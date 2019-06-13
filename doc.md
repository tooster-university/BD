# Political party management app
##### by Tooster

## Requirements

1. database must exist
2. superuser with access to the database must exist

## Important

* if command requires authentication, the `last_active` field is bumped even if the command in "ERROR"
* Command will add new user even if the result status of it is "ERROR"

## Launching

To run the app execute the `run.sh` script:

* with parameter `--init` if this is the first time launching the app
* without `--init` for next sessions

## API

Main app class is `app.py` and it's first ever invocation should be executed with `--init` parameter.


Class `DB_Engine` implements engine for managing the political party database. First ever usage should invoke `init_setup()` to properly setup the schema. `set_verbose()` can be invoked to enable inclusion of error messages in returned data i nthe fied `debug`. Acceptable commands should be passed as one line JSON objects in format `{"command_name:{<arguments in key-value pairs>}"}`. Below is a list of acceptable commands:

* `open <database> <login> <password>` -> `status`
* `leader <timestamp> <password> <member>` -> `status`
* `protest/support <timestamp> <password> <member> <action> <project> [authority]` -> `status`
* `upvote/downvote <timestamp> <password> <member> <action>` -> `status`
* `actions <timestamp> <member> [type] [project|authority]` -> `status, actions list [of type] [for project|by authority]`
* `projects <timestamp> <member> <password> [authority]` -> `status, projects [by authority]`
* `votes <timestamp> <member> <password> [action|project]` -> `status, votes summary [for action | for project]`
* `trolls <timestamp>` -> `list of trolls`

where types are as foolows:

* `<database, login, password>` : `string`
* `<timestamp, member, action, project, authority` : `number`
* `<type>` : `string=<support|protest>`

Each line of output contains JSON object with in format `{"status": <"OK"|"ERROR"> [, "data":<array of rows with cells ordered as in the function definition>]}`

`leader` function should be executed only during the very first app launch with `--init` parameter.

Illformed input may produce undefined behaviour.
