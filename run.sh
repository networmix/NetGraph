#!/bin/bash

set -e

DEFAULT_IMAGE_TAG=ngraph
IMAGE_TAG=${2:-$DEFAULT_IMAGE_TAG}
DEFAULT_CONTAINER_NAME=ngraph_jupyter
CONTAINER_NAME=${3:-$DEFAULT_CONTAINER_NAME}
IMAGE_ID=$(docker images --format "{{.ID}}" $IMAGE_TAG)

USAGE="Usage: $0 COMMAND [IMAGE_TAG] [CONTAINER_NAME]\n"
USAGE+="    COMMAND is what you expect the script to do:\n"
USAGE+="        build - Builds an image from a Dockerfile.\n"
USAGE+="        run - Runs a container and starts Jupyter.\n"
USAGE+="        shell - Attaches to the shell of a running container.\n"
USAGE+="        killall - Stops and removes all running containers based on the image tag.\n"
USAGE+="        forcecleanall - WARNING: Stops and removes all containers and images. This action cannot be undone.\n"
USAGE+="    IMAGE_TAG is the optional Docker image tag (default: $DEFAULT_IMAGE_TAG).\n"
USAGE+="    CONTAINER_NAME is the optional Docker container name (default: $DEFAULT_CONTAINER_NAME).\n"

if [[ $# -lt 1 ]]; then
    echo>&2 "ERROR: Must specify the command"
    printf "$USAGE" >&2
    exit 2
fi

[[ $(uname) -eq "Darwin" ]] && MODHACK="-v /lib/modules:/lib/modules:ro" || MODHACK=""

function build {
    echo "Building docker container with tag $IMAGE_TAG"
    docker build . -t $IMAGE_TAG

    IMAGE_ID=$(docker images --format "{{.ID}}" $IMAGE_TAG)
    echo "Container image id: $IMAGE_ID"
    return 0
}

function run {
    echo "Starting a container with the name $CONTAINER_NAME using $IMAGE_TAG image..."
    CONTAINER_ID=$(docker create --rm -it --name $CONTAINER_NAME -v "$PWD":/root/env -p 8787:8787 --entrypoint=/bin/bash --privileged $MODHACK --cap-add ALL $IMAGE_TAG)
    docker start $CONTAINER_ID
    echo "Started $CONTAINER_ID with the name $CONTAINER_NAME"
    docker exec -it $CONTAINER_ID pip install -e .
    echo "Starting Jupyter in a container. Open http://127.0.0.1:8787/ in your browser."
    docker exec -it $CONTAINER_ID jupyter notebook --port=8787 --no-browser --ip=0.0.0.0 --allow-root --NotebookApp.token='' /root/env
    return 0
}

function shell {
    echo "Attaching to the shell of the running container $CONTAINER_NAME..."
    docker exec -it $CONTAINER_NAME /bin/bash
    return 0
}

function killall {
    echo "Stopping and removing all running containers based on the image tag $IMAGE_TAG..."
    for container_id in $(docker ps -q --filter "ancestor=$IMAGE_TAG"); do
        echo "$(docker kill $container_id) - stopped and removed"
    done

    return 0
}

function forcecleanall {
    echo "WARNING: This will stop and remove all containers and images. This action cannot be undone."
    read -p "Are you sure you want to proceed? (Y/N): " confirm
    if [[ $confirm != [Yy] ]]; then
        echo "Aborting forcecleanall."
        return 1
    fi

    for container in $(docker container ls --format "{{.ID}}"); do docker container kill $container; done
    for container in $(docker container ls -a --format "{{.ID}}"); do docker container rm $container; done
    for image in $(docker images --format "{{.ID}}"); do docker image rm --force $image; done
    echo "Docker has been cleaned up"
    return 0
}

case $1 in
    build)
        echo "Executing BUILD command..."
        build "$@"
        ;;

    run)
        echo "Executing RUN command..."
        run "$@"
        ;;

    shell)
        echo "Executing SHELL command..."
        shell "$@"
        ;;

    killall)
        echo "Executing KILLALL command..."
        killall "$@"
        ;;

    forcecleanall)
        echo "Executing FORCECLEANALL command..."
        forcecleanall "$@"
        ;;

    *)
      echo>&2 "ERROR: Unknown command $1"
        printf "$USAGE" >&2
        exit 2
        ;;
esac