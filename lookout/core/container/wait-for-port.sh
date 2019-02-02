#!/bin/sh -e

if ! which nc; then
  apt update && apt install -y netcat
fi

until nc -z $1 $2; do
  echo "Waiting for $1:$2"
  sleep 1
done
