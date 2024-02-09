# To Generate and view a graph:

1. Install graphviz with `brew install graphviz`
2. Install python dependencies `pip3 install okta pydot`
3. Export your Okta API token `OKTA_TOKEN=<mytoken>`
4. cd into `tests` directory
5. Edit `group_names` and `profile` in gen-graph.py to whatever groups + profile attributes you want to graph
6. Run `python3 gen-graph.py`
7. Start an http server locally with `python3 -m http.server 8080` (If you haven't already)
8. Browse to `http://localhost:8080/index.html` to view interactive graph
9. Run gen-grapy.py with different args to see different traces based in inputs


## TODO
* Implement applications
