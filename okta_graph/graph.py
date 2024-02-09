#!/usr/bin/env python3
import asyncio
from base64 import b64encode
from os import remove
from re import compile
import subprocess
from tempfile import mktemp
from typing import Dict, List, Tuple

from pydot import Dot, Edge, Node

from .plugins import NodePlugin, NullNodePlugin
from . import LOGGER


default_group_node_opts = {
    "fixedsize": "false",
    "height": ".75",
    "width": ".75",
    "labelloc": "b",
    "fontsize": "10.0",
    "shape": "plaintext",
    "imagescale": "false",
}

default_edge_opts = {"fontsize": "5", "dir": "forward"}

default_rule_node_opts = {**default_group_node_opts, "height": ".5", "width": ".5"}

default_manual_assignment_node_opts = default_rule_node_opts
tooltip_title_re = compile(r"_|-")


class OktaGraph:
    """
    Generates a dot file along with corresponding graph image and html for HTML
    image map to be viewed in a browser.
    """

    def __init__(
        self,
        data: Dict[str, Dict],
        edge_opts: Dict[str, str] = {},
        group_node_opts: Dict[str, str] = {},
        icon_dir: str = "static/icons",
        manual_assignment_node_opts: Dict[str, str] = {},
        node_plugin: NodePlugin = NullNodePlugin(),
        rule_node_opts: Dict[str, str] = {},
        temp_dir: str = "/tmp",
    ):
        self.node_plugin = node_plugin
        self.node_plugin_is_async = asyncio.iscoroutinefunction(
            self.node_plugin.make_node
        )

        #: Location of icons used in the graph image
        self.icon_dir = icon_dir
        LOGGER.debug(f"Using {self.icon_dir} for graph icons.")
        #: Prefix where temporary files will be written to
        self.temp_dir = temp_dir

        #: The data that the graph will be generated from
        self.data: Dict[str, Dict] = data

        #: Pydot graph
        self.graph: Dot = Dot("Okta", graph_type="digraph")

        self.group_node_opts = {**default_group_node_opts, **group_node_opts}

        self.rule_node_opts = {**default_rule_node_opts, **rule_node_opts}

        self.manual_assignment_node_opts = {
            **default_manual_assignment_node_opts,
            **manual_assignment_node_opts,
        }

        self.edge_opts = {**default_edge_opts, **edge_opts}

        self.node_opts = {
            "Okta Group": self.group_node_opts,
            "Okta Group Rule": self.rule_node_opts,
            "Manual Group Assignment": self.manual_assignment_node_opts,
        }

        self.graph.set_node_defaults(**self.group_node_opts)
        self.graph.set_edge_defaults(**self.edge_opts)

    @classmethod
    def get_fontsize(cls, name) -> str:
        """
        Calculates the font size for node labels based on the size of
        the node (DPI) and lengh of the node's name.
        """
        return str((72 * 2) / len(name))

    async def __run_node_plugin(self, data: Dict, node: Node) -> Node:
        if isinstance(self.node_plugin, NullNodePlugin):
            return node
        node_name = node.get_name()
        if self.node_plugin_is_async:
            node = await self.node_plugin.make_node(
                data,
                node,
            )
        else:
            node = self.node_plugin.make_node(data, node)

        if node.get_name() != node_name:
            raise AttributeError(
                "Node names are immutable. Plugins must return nodes without altering their name"
            )
        return node

    async def make_node(
        self,
        name: str,
        data: Dict[str, Dict],
        append: bool = True,
        tooltip: Dict[str, str | int | float] = {},
        **kwargs: Dict[str, str],
    ) -> Node:
        """
        Creates a new node, or returns an existing one if a node by that name already exists.
        """
        node_images = {
            "Okta Group": f"{self.icon_dir}/group.png",
            "Okta Group Rule": f"{self.icon_dir}/rule.png",
            "Okta User": f"{self.icon_dir}/user.png",
            "Manual Group Assignment": f"{self.icon_dir}/manual_group.png",
        }

        if not self.graph.get_node(name):
            opts = self.node_opts.get(data["type"], {})
            opts.update(kwargs)
            opts["fontsize"] = self.get_fontsize(name)

            opts["image"] = node_images.get(data["type"], node_images["Okta Group"])

            if tooltip:
                opts["tooltip"] = self.make_tooltip(tooltip)

            node = await self.__run_node_plugin(data, Node(name, **opts))

            if append:
                self.graph.add_node(node)

            return node
        else:
            return self.get_node(name)[0]

    @classmethod
    def make_tooltip(cls, data: Dict[str, Dict]) -> str:
        """
        Generates a string suitable for an HTML lable from a dict
        of metadata.
        """
        label_str = ""
        for k, v in data.items():
            if v is None:
                v = ""
            if not isinstance(v, (str, int, float, bool)):
                continue
            k = tooltip_title_re.sub(" ", k).title()
            label_str += rf"{k}: {v}\n"

        return label_str

    async def add_children(
        self, node: Node, children: List[Dict], recursive: bool = True
    ):
        """
        Add all child nodes, created by the data supplied in `data` to the graph. If `recursive` is `True`
        then all children of `children` will be parsed recursively.
        """
        node_name = node.get_name()

        for child in children:
            child_name = child["name"]
            rule_name = f'RULE - {child["rule_name"]}'

            if ":" in child_name:
                child_name = f'"{child_name}"'

            if ":" in rule_name:
                rule_name = f'"{rule_name}"'

            if child.get("manually_managed"):
                rule_data = {
                    "type": "Manual Group Assignment",
                    "name": f"Manual Assignment to {child_name}",
                    "description": "This group was assigned manually in the query",
                }
            else:
                rule_data = {
                    k: (str(v) if v is not None else "")
                    for k, v in child.items()
                    if k.startswith("rule") and isinstance(v, (str, int, float, bool))
                }
                rule_data["type"] = "Okta Group Rule"

            child_node_data = {
                k: v
                for k, v in child.items()
                if not k.startswith("rule") and isinstance(v, (str, int, float, bool))
            }

            # Create an intermediate node for the rule that is mapping us to the child
            await self.make_node(rule_name, rule_data, label="", tooltip=rule_data)

            # Create the child node
            child_node = await self.make_node(
                child_name, child, tooltip=child_node_data
            )

            # Link the parent node to the rule node
            await self.make_edge(node_name, rule_name)

            # Link the rule node to the child node
            await self.make_edge(rule_name, child_name)

            if recursive:
                await self.add_children(child_node, child.get("children", []))

        return self.graph

    async def make_edge(self, source: str, dest: str, append=True) -> Edge:
        """
        Create an edge or return an existing one if it already exists.
        """
        if not self.graph.get_edge(source, dest):
            edge = Edge(source, dest)
            if append:
                self.graph.add_edge(edge)
        else:
            edge = self.graph.get_edge(source, dest)[0]

        return edge

    async def make_graph(
        self, data: Dict[str, Dict] = {}, as_base64=False
    ) -> Tuple[str, str]:
        """
        Generates a graph image and corresponding HTML map data from `data`. If `as_base64` is `True` then
        both items in the response will be their base64 encoded values. If `as_base64` is `False` then the files
        will be written to disk and the paths to the files returned.
        """
        data = data or self.data

        gids = [x["group_id"] for x in data.values() if x.get("manually_managed")]
        gid_str = ", ".join(gids)
        profile_tooltip = {
            "name": "Okta User",
            "group_ids_queried": gid_str,
            "type": "Okta User",
        }
        profile_root = await self.make_node(
            "Okta User", profile_tooltip, tooltip=profile_tooltip
        )

        await self.add_children(profile_root, list(data.values()))

        dot_file = mktemp(dir=f"{self.temp_dir}/dots")
        img_file = mktemp(dir=f"{self.temp_dir}/images")
        map_file = mktemp(dir=f"{self.temp_dir}/maps")

        self.graph.write_dot(dot_file)

        cmd = [
            "dot",
            "-T",
            "cmap",
            "-o",
            map_file,
            "-T",
            "png",
            "-o",
            img_file,
            dot_file,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        LOGGER.debug(res.stdout.decode())
        LOGGER.debug(res.stderr.decode())

        remove(dot_file)

        if as_base64:
            with open(img_file, "rb") as f:
                img = b64encode(f.read())

            with open(map_file, "rb") as f:
                cmap = b64encode(f.read())

            remove(img_file)
            remove(map_file)

            return img.decode(), cmap.decode()

        else:
            return img_file, map_file
