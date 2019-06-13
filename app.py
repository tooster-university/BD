import json
import sys
import db_engine as DB


def main(arg):
    engine = DB.DB_Engine()

    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        engine.init_setup()

    # engine.set_verbose()
    for line in sys.stdin.readlines():
        cmd = json.loads(line)
        retval = engine.execute_command(cmd)
        print(json.dumps(retval))
        if 'open' in cmd and retval['status'] != "OK":
            return

if __name__ == "__main__":
    main(sys.argv)