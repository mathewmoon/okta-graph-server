#!/usr/bin/env bash

function install() {
    if [[ -z "$(which brew)" ]]; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
    fi

    if [[ -z "$(which python3.12)" ]]; then
        brew install python@3.12
    fi

    if [[ -z "$(which dot)" ]]; then
        brew install graphviz
    fi

    pip3 install -r ./requirements.txt   
}

function help() {
    cat <<'EOF'
    To run the server:
        - You will need to export your Okta API key as OKTA_TOKEN
        - cd into ../okta-graph
        - If you want to cache data from Okta locally run the following commands `./install.sh make-cache`:
            - This will create group_data.json and rules.json by querying Okta for all groups and rules
            - Once the data is loaded anytime you export `LOCAL_DATA=true` before running the server you will get data out of the cache to speed up queries.
    
        - run `uvicorn api:app` or `./install.sh server` to start the server
        - The server will be running at http://localhost:8000
EOF
}

function make_cache() {
    export WRITE_GROUP_DATA=true
    echo "Building data cache. This may take up to 10 seconds"
    timeout 10 uvicorn api:app
    unset WRITE_GROUP_DATA
    export LOCAL_DATA=true
}

if [[ "$1" = "make-cache" ]]; then
    make_cache
elif [[ "$1" = "server" ]]; then
    uvicorn api:app
else
    install
fi

help
