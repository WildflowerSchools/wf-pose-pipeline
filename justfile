
build:
    docker build -f docker/Dockerfile-frameextract -t wildflowerschools/wf-pose-pipeline:frameextract-v0 .

run-container:
    docker run --network host -it --entrypoint bash -v $PWD/scripts:/scripts -v /data:/data wildflowerschools/wf-pose-pipeline:frameextract-v0


# python entrypoint.py queue-jobs --environment d66e49ab-52da-40d3-9ba1-96e35b71b14e --tz US/Pacific --reprocess-date 2023-01-06 --verbose