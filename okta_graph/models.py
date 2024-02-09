#!/usr/bin/env python3
from datetime import datetime
from typing import Any, Callable, Dict, List

from pydot import Node
from pydantic import BaseModel, PrivateAttr

from .graph import OktaGraph
from .rule_parser import Parser


class QueryResult(BaseModel):
    image: str
    map: str
    report_json: Dict[str, Dict | str]


class GraphQuery(BaseModel):
    group_name_input: List[str] = []
    groupid_input: List[str] = []
    profile_input: Dict[str, Any] = {}

    _data: Dict = PrivateAttr({})
    _query_opts: Dict = PrivateAttr({})

    async def do_query(
        self, groups: Dict[str, Dict], rules: List[Dict[str, Dict]]
    ) -> Dict[str, Dict[str, Dict]]:
        """
        Returns a dictionary containting the graph image, html for the image map,
        and the raw json the graph was generated with.
        """
        self._query_opts.update(
            {
                "groups": groups,
                "rules": rules,
                "profile_input": self.profile_input,
                "group_name_input": self.group_name_input,
                "groupid_input": self.groupid_input,
            }
        )

        parser = Parser(**self._query_opts)
        self._data = await parser.parse()
        return self._data

    async def make_graph(
        self,
        *,
        temp_dir,
        icon_dir: str = "static/icons",
        groups: Dict[str, Dict],
        rules: List[Dict[str, Dict]],
        as_base64: bool = True,
        node_plugin: Callable[[Dict, Node], Node] | None = None
    ) -> QueryResult:
        await self.do_query(groups, rules)

        graph = OktaGraph(
            self._data, temp_dir=temp_dir, icon_dir=icon_dir, node_plugin=node_plugin
        )

        img_data, map_data = await graph.make_graph(as_base64=as_base64)

        opts = self._query_opts
        del opts["groups"]
        del opts["rules"]
        date = datetime.now().isoformat()

        report = {"query_date": date, "query": opts, "result": self._data}

        res = QueryResult(image=img_data, map=map_data, report_json=report)

        return res
