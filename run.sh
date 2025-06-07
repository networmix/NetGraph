#!/bin/bash

set -e

DEFAULT_IMAGE_TAG="ngraph"
DEFAULT_CONTAINER_NAME="ngraph_jupyter"
DEFAULT_PORT=8788

# Initialize variables with default values
IMAGE_TAG="$DEFAULT_IMAGE_TAG"
CONTAINER_NAME="$DEFAULT_CONTAINER_NAME"
PORT="$DEFAULT_PORT"

USAGE="Usage: $0 COMMAND [-i IMAGE_TAG] [-c CONTAINER_NAME] [-p PORT]\n"
USAGE+="    COMMAND is required:\n"
USAGE+="        build - Builds an image from a Dockerfile.\n"
USAGE+="        run - Runs a container and starts JupyterLab.\n"
USAGE+="        stop - Stops a running container.\n"
USAGE+="        shell - Attaches to the shell of a running container.\n"
USAGE+="        killall - Stops and removes all containers based on the image tag.\n"
USAGE+="        forcecleanall - WARNING: Stops and removes all containers and images. This action cannot be undone.\n"
USAGE+="    -i IMAGE_TAG: Optional Docker image tag (default: $DEFAULT_IMAGE_TAG)\n"
USAGE+="    -c CONTAINER_NAME: Optional Docker container name (default: $DEFAULT_CONTAINER_NAME)\n"
USAGE+="    -p PORT: Optional port for JupyterLab (default: $DEFAULT_PORT)\n"

# Check if at least one argument is provided
if [[ $# -lt 1 ]]; then
    echo >&2 "ERROR: Must specify the command"
    printf "%b" "$USAGE" >&2
    exit 2
fi

# Extract the command
COMMAND="$1"
shift

# Parse named parameters
while getopts ":i:c:p:" opt; do
  case "$opt" in
    i)
      IMAGE_TAG="$OPTARG"
      ;;
    c)
      CONTAINER_NAME="$OPTARG"
      ;;
    p)
      PORT="$OPTARG"
      ;;
    \?)
      echo "Invalid option: -$OPTARG" >&2
      printf "%b" "$USAGE" >&2
      exit 1
      ;;
    :)
      echo "Option -$OPTARG requires an argument." >&2
      printf "%b" "$USAGE" >&2
      exit 1
      ;;
  esac
done
shift $((OPTIND -1))

# MODHACK is a workaround for Docker on macOS
if [[ "$(uname)" == "Darwin" ]]; then
    MODHACK="-v /lib/modules:/lib/modules:ro"
else
    MODHACK=""
fi

function build {
    echo "Building Docker image with tag '$IMAGE_TAG'..."
    docker build . -t "$IMAGE_TAG"
    echo "Docker image '$IMAGE_TAG' built successfully."
    return 0
}

function run {
    # Check if the image exists locally
    if [[ -z "$(docker images -q "$IMAGE_TAG")" ]]; then
        echo "Error: Docker image '$IMAGE_TAG' not found locally."
        echo "Please run './run.sh build' to build the image first."
        exit 1
    fi

    echo "Starting a container with the name '$CONTAINER_NAME' using the image '$IMAGE_TAG' on port '$PORT'..."

    # Check if a container with the exact name exists
    container_id=$(docker ps -aq -f "name=^/${CONTAINER_NAME}$")

    if [[ -n "$container_id" ]]; then
        # Stop the container if it's running
        if docker ps -q -f "name=^/${CONTAINER_NAME}$" > /dev/null; then
            echo "Stopping existing container with the name '$CONTAINER_NAME'..."
            docker stop "$CONTAINER_NAME" > /dev/null
        fi

        # Remove the container if it's stopped
        if docker ps -aq -f status=exited -f "name=^/${CONTAINER_NAME}$" > /dev/null; then
            echo "Removing stopped container with the name '$CONTAINER_NAME'..."
            docker rm "$CONTAINER_NAME" > /dev/null
        fi
    fi

    # Create and start a new container
    CONTAINER_ID=$(docker create -it --name "$CONTAINER_NAME" \
        -v "$PWD":/root/env -p "$PORT":$PORT $MODHACK \
        --entrypoint=/bin/bash --privileged --cap-add ALL "$IMAGE_TAG")
    docker start "$CONTAINER_ID"
    echo "Started container with ID '$CONTAINER_ID' and name '$CONTAINER_NAME'"

    # Install the package inside the container
    docker exec -it "$CONTAINER_ID" pip install -e .
    echo "Package installed inside the container."

    # Start JupyterLab
    echo "Starting JupyterLab in the container. Open http://127.0.0.1:$PORT/ in your browser."
    docker exec -it "$CONTAINER_ID" jupyter lab --port=$PORT \
        --no-browser --ip=0.0.0.0 --allow-root --NotebookApp.token='' /root/env/notebooks
    return 0
}

function stop {
    echo "Stopping the container '$CONTAINER_NAME'..."
    docker stop "$CONTAINER_NAME" > /dev/null || echo "Container '$CONTAINER_NAME' is not running."
    return 0
}

function shell {
    echo "Attaching to the shell of the running container '$CONTAINER_NAME'..."
    docker exec -it "$CONTAINER_NAME" /bin/bash
    return 0
}

function killall {
    echo "Stopping all running containers based on the image tag '$IMAGE_TAG'..."
    for container_id in $(docker ps -q --filter "ancestor=$IMAGE_TAG"); do
        echo "Stopping container ID: '$container_id'"
        docker kill "$container_id" > /dev/null
    done

    echo "Removing all containers based on the image tag '$IMAGE_TAG'..."
    for container_id in $(docker ps -aq --filter "ancestor=$IMAGE_TAG"); do
        echo "Removing container ID: '$container_id'"
        docker rm "$container_id" > /dev/null
    done
    return 0
}

function forcecleanall {
    echo "WARNING: This will stop and remove all containers and images. This action cannot be undone."
    read -rp "Are you sure you want to proceed? (Y/N): " confirm
    if [[ "$confirm" != [Yy] ]]; then
        echo "Aborting forcecleanall."
        return 1
    fi

    echo "Stopping all running containers..."
    for container_id in $(docker container ls -q); do
        echo "Stopping container ID: '$container_id'"
        docker container kill "$container_id"
    done

    echo "Removing all containers..."
    for container_id in $(docker container ls -aq); do
        echo "Removing container ID: '$container_id'"
        docker container rm "$container_id"
    done

    echo "Removing all images..."
    for image_id in $(docker images -q); do
        echo "Removing image ID: '$image_id'"
        docker image rm --force "$image_id"
    done

    echo "Docker has been cleaned up."
    return 0
}

case "$COMMAND" in
    build)
        echo "Executing BUILD command..."
        build "$@"
        ;;
    run)
        echo "Executing RUN command..."
        run "$@"
        ;;
    stop)
        echo "Executing STOP command..."
        stop "$@"
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
        echo >&2 "ERROR: Unknown command '$COMMAND'"
        printf "%b" "$USAGE" >&2
        exit 2
        ;;
esac
