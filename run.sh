#!/bin/bash

set -e

DEFAULT_IMAGE_TAG=ngraph
IMAGE_TAG=${2:-$DEFAULT_IMAGE_TAG}
DEFAULT_CONTAINER_NAME=ngraph_jupyter
CONTAINER_NAME=${3:-$DEFAULT_CONTAINER_NAME}
IMAGE_ID=$(docker images --format "{{.ID}}" "$IMAGE_TAG")

USAGE="Usage: $0 COMMAND [IMAGE_TAG] [CONTAINER_NAME]\n"
USAGE+="    COMMAND is what you expect the script to do:\n"
USAGE+="        build - Builds an image from a Dockerfile.\n"
USAGE+="        run - Runs a container and starts Jupyter.\n"
USAGE+="        shell - Attaches to the shell of a running container.\n"
USAGE+="        killall - Stops and removes all containers based on the image tag.\n"
USAGE+="        forcecleanall - WARNING: Stops and removes all containers and images. This action cannot be undone.\n"
USAGE+="    IMAGE_TAG is the optional Docker image tag (default: $DEFAULT_IMAGE_TAG).\n"
USAGE+="    CONTAINER_NAME is the optional Docker container name (default: $DEFAULT_CONTAINER_NAME).\n"

if [[ $# -lt 1 ]]; then
    echo >&2 "ERROR: Must specify the command"
    printf "$USAGE" >&2
    exit 2
fi

# MODHACK is a workaround for Docker on macOS
if [[ "$(uname)" == "Darwin" ]]; then
    MODHACK="-v /lib/modules:/lib/modules:ro"
else
    MODHACK=""
fi

function build {
    echo "Building docker container with tag $IMAGE_TAG"
    docker build . -t "$IMAGE_TAG"

    IMAGE_ID=$(docker images --format "{{.ID}}" "$IMAGE_TAG")
    echo "Container image ID: $IMAGE_ID"
    return 0
}

function run {
    # Check if the image exists locally
    if [[ -z "$(docker images -q "$IMAGE_TAG")" ]]; then
        echo "Error: Docker image '$IMAGE_TAG' not found locally."
        echo "Please run './run.sh build' to build the image first."
        exit 1
    fi

    echo "Starting a container with the name $CONTAINER_NAME using $IMAGE_TAG image..."

    # Check if a container with the exact name exists
    container_id=$(docker ps -aq -f name=^/${CONTAINER_NAME}$)

    if [[ -n "$container_id" ]]; then
        # Stop the container if it's running
        if docker ps -q -f name=^/${CONTAINER_NAME}$ > /dev/null; then
            echo "Stopping existing container with the name $CONTAINER_NAME..."
            docker stop "$CONTAINER_NAME" > /dev/null
        fi

        # Remove the container if it exists
        if docker ps -aq -f name=^/${CONTAINER_NAME}$ > /dev/null; then
            echo "Removing existing container with the name $CONTAINER_NAME..."
            docker rm "$CONTAINER_NAME" > /dev/null
        fi
    fi

    # Create and start a new container
    CONTAINER_ID=$(docker create -it --name "$CONTAINER_NAME" \
        -v "$PWD":/root/env -p 8787:8787 $MODHACK \
        --entrypoint=/bin/bash --privileged --cap-add ALL "$IMAGE_TAG")
    docker start "$CONTAINER_ID"
    echo "Started container with ID $CONTAINER_ID and name $CONTAINER_NAME"

    # Install the package inside the container
    docker exec -it "$CONTAINER_ID" pip install -e .
    echo "Starting Jupyter in the container. Open http://127.0.0.1:8787/ in your browser."

    # Start Jupyter Notebook
    docker exec -it "$CONTAINER_ID" jupyter notebook --port=8787 \
        --no-browser --ip=0.0.0.0 --allow-root --NotebookApp.token='' /root/env/notebooks
    return 0
}

function shell {
    echo "Attaching to the shell of the running container $CONTAINER_NAME..."
    docker exec -it "$CONTAINER_NAME" /bin/bash
    return 0
}

function killall {
    echo "Stopping all running containers based on the image tag $IMAGE_TAG..."
    for container_id in $(docker ps -q --filter "ancestor=$IMAGE_TAG"); do
        echo "Stopping container ID: $container_id"
        docker kill "$container_id" > /dev/null
    done

    echo "Removing all containers based on the image tag $IMAGE_TAG..."
    for container_id in $(docker ps -aq --filter "ancestor=$IMAGE_TAG"); do
        echo "Removing container ID: $container_id"
        docker rm "$container_id" > /dev/null
    done
    return 0
}

function forcecleanall {
    echo "WARNING: This will stop and remove all containers and images. This action cannot be undone."
    read -p "Are you sure you want to proceed? (Y/N): " confirm
    if [[ "$confirm" != [Yy] ]]; then
        echo "Aborting forcecleanall."
        return 1
    fi

    echo "Stopping all running containers..."
    for container_id in $(docker container ls -q); do
        echo "Stopping container ID: $container_id"
        docker container kill "$container_id"
    done

    echo "Removing all containers..."
    for container_id in $(docker container ls -aq); do
        echo "Removing container ID: $container_id"
        docker container rm "$container_id"
    done

    echo "Removing all images..."
    for image_id in $(docker images -q); do
        echo "Removing image ID: $image_id"
        docker image rm --force "$image_id"
    done

    echo "Docker has been cleaned up."
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
        echo >&2 "ERROR: Unknown command $1"
        printf "$USAGE" >&2
        exit 2
        ;;
esac