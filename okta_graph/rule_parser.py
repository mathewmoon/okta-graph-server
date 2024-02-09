#!/usr/bin/env python3
from hashlib import sha256
from re import compile
from typing import Any, Dict, List

from . import LOGGER

from okta_expression_parser.parser import ExpressionParser


MEMBER_RULE_REGEX = compile(r".*isMemberOf.*")
GID_REGEX = compile(r'"[a-zA-Z0-9]{20}"')


class Parser:
    """
    Takes a hypothetical user configuration, including profile attributes and manual group assignments
    and returns a dict suitable for passing to `okta_graph.Graph`
    """

    def __init__(
        self,
        groupid_input: List[str] = [],
        profile_input: Dict[str, Any] = {},
        group_name_input: List[str] = [],
        rules: List[Dict[str, Any]] = [],
        groups: Dict[str, Any] = {},
    ):
        #: A dict containting key/value pairs that will be used as the user's Okta profile in the query
        self.profile: Dict[str, Any] = profile_input

        self._groups: Dict[str, str] = groups
        self._rules: Dict[str, Any] = rules
        self._groups_by_name: Dict[str, str] = {
            v["profile"]["name"]: v for v in self._groups.values()
        }
        group_ids_by_name = [
            x["id"]
            for x in self._groups_by_name.values()
            if x["profile"]["name"] in group_name_input
        ]

        #: The combination of `groupid_input` and `group_name_input` values resolved to their true group ID's
        self.__groupids: List[str] = []
        self.append_groupids(groupid_input + group_ids_by_name)

        self.__match_cache = {}

    @property
    def groupids(self) -> List[str]:
        self.__groupids = sorted(list(set(self.__groupids)))
        return self.__groupids

    def append_groupids(self, ids: str | List[str]):
        if isinstance(ids, str):
            ids = [ids]
        self.__groupids += ids
        return self.groupids

    def sorted_list(self, data: List[str]):
        return sorted(list(set(data)))

    def matches_groupids(self, gids: List[str]) -> bool:
        gids = sorted(list(set(gids)))
        return self.groupids == gids

    def make_human_readable_expression(self, exp: str) -> str:
        """
        Takes an Okta group expression and replaces group ID's with
        group names for human readability
        """
        if ids := GID_REGEX.findall(exp):
            ids = [x.replace('"', "") for x in ids]
        else:
            return exp

        for id in ids:
            if group := self._groups.get(id):
                exp = exp.replace(id, group["profile"]["name"])

        return exp

    def get_group_rules(self) -> List[Dict]:
        """
        Returns only rules that use groupid membership tests in their expression.
        """
        rules = []
        for rule in self._rules:
            exp = rule["conditions"]["expression"]["value"]
            if MEMBER_RULE_REGEX.match(exp):
                rules.append(rule)

        return rules

    def make_cache_key(self, gid, map_to_id):
        hash_str = gid + map_to_id + str(self.groupids)
        cache_key = sha256(hash_str.encode()).hexdigest()
        return cache_key

    async def parse(self) -> Dict:
        """
        Builds out our response data.
        """
        new_gids = []
        res = {}

        # Get gid's from groups that are inherited by profile alone. EG: rules that don't
        # only require user attributes, and not group membership, to pass
        manual_groups = self.groupids

        profile_res, profile_gids = await self.parse_group(
            group_rules_only=False, profile_only=True
        )
        profile_res = {x["name"]: x for x in profile_res}

        self.append_groupids(profile_gids)

        # Iterate over the gid's that were passed as args, adding any new gid's that
        # our user would inherit to self.groupids and iterating again. We'll continue on
        # until self.groupids is no longer growing.
        _first = True

        n = 1
        while True:
            LOGGER.info(f"Iterating over group ID's: {n}")
            for id in self.groupids:
                # Create the root nodes:
                group = self._groups[id]
                group_name = group["profile"]["name"]

                if group_name in profile_res:
                    group_info = profile_res[group_name]
                else:
                    group_info = {
                        "name": group_name,
                        "type": "Okta Group",
                        "description": group["profile"].get("description", ""),
                        "group_id": id,
                        "group_name": group_name,
                    }

                if id in manual_groups:
                    group_info["manually_managed"] = True
                    group_info["rule_name"] = f"Group {group_name} manual membership"
                    group_info[
                        "description"
                    ] = "This group was manually passed in the query."

                children, gids = await self.parse_group(gid=id, group_rules_only=True)
                if children:
                    group_info["children"] = children

                if _first:
                    res[group_name] = group_info

                new_gids = self.sorted_list(self.groupids + new_gids + gids)

            # if they match then break so we can return our res
            _first = False

            if new_gids == self.groupids:
                break

            # Update self.groupids with the new gids and iterate again
            self.append_groupids(new_gids)

            n += 1
        return res

    async def parse_group(
        self, gid="", _first=True, group_rules_only=True, profile_only=False
    ):
        res = []
        matched_gids = []

        if _first:
            rules = self.get_group_rules() if group_rules_only else self._rules

        else:
            # Any expression that doesn't rely on matching groups HAS to be applied at
            # the root level, otherwise it will get nested in some seemingly random
            # node on the graph
            rules = self.get_group_rules()

        if group_rules_only:
            rules = self.get_group_rules()
            rules = [
                x for x in rules if f'"{gid}"' in x["conditions"]["expression"]["value"]
            ]

        else:
            rules = self._rules

        for rule in rules:
            exp = rule["conditions"]["expression"]["value"]

            map_to = self.sorted_list(
                [
                    x
                    for x in rule["actions"]["assignUserToGroups"]["groupIds"]
                    if x in self._groups
                ]
            )

            try:
                test = ExpressionParser(
                    group_ids=[] if profile_only else self.groupids,
                    log_to_stdout=False,
                    user_profile=self.profile,
                ).parse(exp)
                LOGGER.debug(f"Expression: {exp} == {test}")
            except (RecursionError, Exception) as e:
                LOGGER.error(f"{type(e)} error while parsing expression {exp}")
                LOGGER.exception(e)
                test = False

            if test:
                matched_gids = self.sorted_list(map_to + matched_gids)

                for id in map_to:
                    cache_key = self.make_cache_key(gid, id)
                    if cache_key in self.__match_cache:
                        children = self.__match_cache[cache_key]
                        gids = []
                        recursion = True
                    else:
                        children, gids = await self.parse_group(gid=id, _first=False)
                        self.__match_cache[cache_key] = children
                        recursion = False

                    matched_gids = self.sorted_list(gids + matched_gids)

                    res.append(
                        {
                            "name": self._groups[id]["profile"]["name"],
                            "type": "Okta Group",
                            "description": self._groups[id]["profile"].get(
                                "description", ""
                            ),
                            "rule": rule,
                            "rule_name": rule["name"],
                            "rule_id": rule["id"],
                            "rule_exp": rule["conditions"]["expression"]["value"],
                            "rule_readable_expression": self.make_human_readable_expression(
                                rule["conditions"]["expression"]["value"]
                            ),
                            "group_id": id,
                            "group_name": self._groups[id]["profile"]["name"],
                            "children": children,
                            "is_recursion": recursion,
                        }
                    )

        return res, matched_gids
