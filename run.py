#!/usr/bin/env python3
from argparse import ArgumentParser
import logging
import os

import okta_graph.api
from okta_graph.plugins import AWSNodePlugin
from okta.client import Client as OktaClient
from okta_graph.api import OktaGraphServer
from okta_graph.cache import OktaFileCache


logging.getLogger("botocore").setLevel("WARN")


OKTA_TOKEN = os.environ["OKTA_TOKEN"]
graph_mod_path = os.path.abspath(os.path.dirname(okta_graph.api.__file__))

parser = ArgumentParser()
parser.add_argument(
    "--temp-dir", help="Prefix for storing temp files.", type=str, default="/tmp"
)
parser.add_argument(
    "--static-dir",
    help="The root from which static content is served.",
    type=str,
    default=os.path.join(graph_mod_path, "static"),
)
args = parser.parse_args()


def main():
    idstore_id = "d-9067a43fe5"
    sso_instance_arn = "arn:aws:sso:::instance/ssoins-7223271c917338a2"

    okta_token = os.environ["OKTA_TOKEN"]
    okta_url: str = f"https://hingehealth-wf.okta.com"
    okta_client = OktaClient({"orgUrl": okta_url, "token": okta_token})

    cache = OktaFileCache(
        okta_client=okta_client,
        persist=True,
        refresh_interval=120,
        groups_file="cached_groups.json",
        rules_file="cached_rules.json",
    )

    plugin = AWSNodePlugin(
        identitystore_id=idstore_id,
        sso_instance_arn=sso_instance_arn,
        dev_mode=True if os.environ.get("DEV_MODE") else False,
        icon_dir=f"{args.static_dir}/icons",
    )

    server = OktaGraphServer(
        cache=cache,
        temp_dir=args.temp_dir,
        static_content_dir=args.static_dir,
        node_plugin=plugin,
    )

    server.run(reload=False)


if __name__ == "__main__":
    main()
