#!/bin/sh -e

until PGPASSWORD="$4" psql -h $1 -p $2 -U $3 -c '\q'; do
  echo "Waiting for Postgres"
  sleep 1
done
