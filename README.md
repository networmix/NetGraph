# NetGraph

🚧 Work in progress! 🚧

## How to use

1. Clone this repo (or download as ZIP archive)
1. Build docker image:

    ```text
    docker build -t netgraph .
    ```

1. Run a container:

    ```text
    docker run -it --rm --hostname netgraph --name netgraph-running -p 8888:8888 netgraph
    ```

1. Upon startup your container started a Jupyter Notebook Server that printed a bunch of text. There should be a URL looking similar to:

    ```text
    http://127.0.0.1:8888/?token=553ef7c73f079ac51936b542f64cf58b7ea8da6561499350
    ```

1. Copy/paste the URL into your browser. It should open Jupyter Notebook App window.