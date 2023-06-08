CURRENT_DIR = $(shell pwd)
PROJECT_NAME = tg_api
include .env
export

build:
	docker build -t ${PROJECT_NAME}:dev .

run:
	docker run --rm \
	    --env-file ${CURRENT_DIR}/.env \
	    -v "${CURRENT_DIR}/src:/srv/src" \
	    --name ${PROJECT_NAME}_container \
	    ${PROJECT_NAME}:dev

stop:
	docker rm -f ${PROJECT_NAME}_container
