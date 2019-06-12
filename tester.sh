#!/usr/bin/env bash

# Provide your executable name
PROGRAM="./app.py"

set PGPASSWORD=T3sT3ro
set PGUSER=postgres
set PGDATABASE=postgres

cleanup() {
    # Cleanup the database the way you like
    psql -c "DROP DATABASE student"
    psql -c "DROP OWNED BY app; DROP USER app"
    psql -c "CREATE DATABASE student OWNER init"
}

folder="$1"

echo "Loading tests from $folder"

test_names=`ls $folder | grep \.init\.in | sed 's/\.init\.in$//g'`

for test_name in $test_names
do
    test="$folder/$test_name"
    cleanup > /dev/null 2>&1
    echo -n "Test $test: "
    if diff <($PROGRAM --init < $test.init.in) $test.init.out > /dev/null
    then
        if diff <($PROGRAM < $test.rest.in) $test.rest.out > /dev/null
        then
            echo "OK"
        else
            echo "Rest bad"
        fi
    else
        echo "Init Bad"
    fi
done
