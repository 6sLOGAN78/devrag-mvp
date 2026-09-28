#!/bin/bash
set -a
source docker/.env
set +a
envsubst < conf/service_conf.yaml.template > conf/service_conf.yaml
echo "Generated conf/service_conf.yaml"
