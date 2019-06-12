import psycopg2
from enum import Enum
from decimal import Decimal


class Mode(Enum):
    NONE = 0
    USER = 1
    LEADER = 2


class Command():

    def __init__(self, engine, mode, binding):
        self.engine = engine
        self.mode = mode
        self.binding = binding

    # converts tuples from result_set to arrays, Decimals to int literals
    def __sanitize_types__(self, data):
        for i in range(len(data)): # map tuples to arrays in place
            data[i] = list(data[i])
            for j in range(len(data[i])):
                if isinstance(data[i][j], Decimal):
                    data[i][j] = int(data[i][j])
                if isinstance(data[i][j], bool):
                    data[i][j] = ('true' if data[i][j] else 'false')
        return data

    def execute(self, args):
        success, data = False, None

        retval = {}
        try:
            # execute if timestamp not needed ('open') or timestamp > last tiemstamp
            if 'timestamp' not in args or args['timestamp'] > self.engine.timestamp:
                if self.engine.db_auth(self.mode, args):
                    success, data = self.binding(args)
        except Exception as e:  # all exceptions are caught and status remains failed
            retval['debug'] = str(e)

        if not success:
            retval['status'] = 'ERROR'
        else:
            retval['status'] = 'OK'
            # bump timestamp on success
            if 'timestamp' in args:
                self.engine.timestamp = args['timestamp']
                            # update last activity
                cur = self.engine.connection.cursor()
                cur.execute("UPDATE users SET last_activity=to_timestamp({})::timestamp WHERE user_id = {};".format(
                            args['timestamp'], args['member']))
                cur.close()

            if data is not None:
                retval['data'] = self.__sanitize_types__(data)
        return retval


class DB_Engine():

    def __init__(self):
        self.connection = None
        self.timestamp = 0
        self.commands = {
            "open":     Command(self, Mode.NONE, self.db_open),
            "leader":   Command(self, Mode.NONE, self.db_leader),
            "support":  Command(self, Mode.USER, lambda args: self.db_add_action(+1, args)),
            "protest":  Command(self, Mode.USER, lambda args: self.db_add_action(-1, args)),
            "upvote":   Command(self, Mode.USER, lambda args: self.db_vote(+1, args)),
            "downvote": Command(self, Mode.USER, lambda args: self.db_vote(-1, args)),
            "actions":  Command(self, Mode.LEADER, self.db_actions),
            "projects": Command(self, Mode.LEADER, self.db_projects),
            "votes":    Command(self, Mode.LEADER, self.db_votes),
            "trolls":   Command(self, Mode.NONE, self.db_trolls)
        }
        self.init_setup_flag = False

    def init_setup(self):
        self.init_setup_flag = True

    def execute_command(self, command):
        for alias in command:  # there is only one key in command
            return self.commands[alias].execute(command[alias])

    # manages authentication, timestamp bumping and creating users for Mode.USER commands
    def db_auth(self, mode, auth_data):
        if(mode == Mode.NONE):
            return True

        cur = self.connection.cursor()
        cur.execute("""SELECT is_leader, last_activity FROM users 
                        WHERE user_id = {} AND pwd_hash = crypt('{}', pwd_hash);""".format(
            auth_data['member'], auth_data['password']))
        row = cur.fetchone()
        cur.close()
        # member doesn't exist or auth error
        if row is None:
            if mode == Mode.USER:  # create new member
                cur = self.connection.cursor()
                # add new user
                cur.execute("""INSERT INTO users VALUES 
                                ({}, crypt('{}', gen_salt('md5')), FALSE, to_timestamp({})::timestamp, 0, 0);""".format(
                    auth_data['member'], auth_data['password'], auth_data['timestamp']))
                # exception thrown if user exists means auth error
                # otherwise new user was created
                cur.close()
                return True
            else: # auth error or leader doesn't exist
                return False
        # member exists AKA auth succeeded:
        else:
            # check if frozen
            cur = self.connection.cursor()
            # let SQL handle leap years and other shenanigans
            cur.execute( 
                """SELECT is_leader FROM users WHERE user_id = {} 
                    AND to_timestamp({})::timestamp <= last_activity + INTERVAL '1 year';""".format(
                        auth_data['member'], auth_data['timestamp']))
            row = cur.fetchone()
            if row is None:
                return False  # user is frozen

            # # update last activity
            # cur.execute("UPDATE users SET last_activity=to_timestamp({})::timestamp WHERE user_id = {};".format(
            #     auth_data['timestamp'], auth_data['member']))

            cur.close()
            # check permissions
            return mode == Mode.USER or mode == Mode.LEADER and row[0]

    def db_open(self, args):
        self.connection = psycopg2.connect("dbname={} user={} password={}".format(
            args['database'], args['login'], args['password']))
        self.connection.set_session(autocommit=True)

        if self.init_setup_flag:
            cur = self.connection.cursor()
            cur.execute(open("database.sql", "r").read())
            cur.close()
            self.init_setup_flag = False
        return True, None

    def db_leader(self, args):

        cur = self.connection.cursor()
        cur.execute("INSERT INTO users VALUES ({}, crypt('{}', gen_salt('md5')), TRUE, to_timestamp({})::timestamp, 0, 0);".format(
            args['member'], args['password'], args['timestamp']))
        cur.close()
        return True, None

    def db_add_action(self, karma, args):
        if 'authority' not in args:  # when authority is ommitted
            args['authority'] = 0

        cur = self.connection.cursor()
        cur.execute("INSERT INTO actions VALUES ({}, {}, {}, {}, {}, 0, 0)".format(
            args['action'], args['project'], args['member'], args['authority'], 'TRUE' if karma > 0 else 'FALSE'))
        cur.close()
        return True, None

    def db_vote(self, karma, args):
        cur = self.connection.cursor()
        # nonexisting action results in foreign key violation
        cur.execute("INSERT INTO votes VALUES ({}, {}, {});".format(
            args['member'], args['action'], 'TRUE' if karma > 0 else 'FALSE'))
        cur.close()
        return True, None

    def db_actions(self, args):
        type_subquery = "AND is_support = {}".format(
            'TRUE' if args['type'] == 'support' else 'FALSE') if 'type' in args else ""
        project_subquery = "AND project_id = {}".format(
            args['project']) if 'project' in args else ""
        authority_subquery = "AND authority_id = {}".format(
            args['authority']) if 'authority' in args else ""
        cur = self.connection.cursor()
        cur.execute("""SELECT action_id, 
                        (CASE WHEN is_support THEN 'support' ELSE 'protest' END) AS type,
                        project_id,
                        authority_id,
                        upvotes,
                        downvotes FROM actions WHERE TRUE {} {} {} ORDER BY action_id;""".format(
            type_subquery, project_subquery, authority_subquery))
        rows = cur.fetchall()
        cur.close()
        return True, rows

    def db_projects(self, args):
        authority_subquery = "AND authority_id = {}".format(
            args['authority']) if 'authority' in args else ""
        cur = self.connection.cursor()
        cur.execute("""SELECT DISTINCT project_id, authority_id FROM actions WHERE TRUE {}
                        ORDER BY project_id;""".format(
            authority_subquery))
        rows = cur.fetchall()
        cur.close()
        return True, rows

    def db_votes(self, args):
        authority_subquery = "AND authority_id = {}".format(
            args['authority']) if 'authority' in args else ""
        project_subquery = "AND project_id = {}".format(
            args['project']) if 'project' in args else ""
        cur = self.connection.cursor()
        cur.execute("""
            WITH votes_full AS (
                SELECT v.user_id, is_upvote FROM votes v JOIN actions USING (action_id) WHERE TRUE {0} {1})
                    (SELECT user_id, 0 as upvotes, 0 as downvotes FROM users
                        WHERE user_id NOT IN (SELECT user_id FROM votes_full))
                    UNION
                    (SELECT user_id, 
                            COUNT(CASE WHEN is_upvote THEN 1 END) AS upvotes, 
                            COUNT(CASE WHEN NOT is_upvote THEN 1 END) AS downvotes 
                        FROM votes_full WHERE TRUE {0} {1} GROUP BY user_id)
                    ORDER BY user_id;""".format(authority_subquery, project_subquery))
        rows = cur.fetchall()
        cur.close()
        return True, rows

    def db_trolls(self, args):
        cur = self.connection.cursor()
        cur.execute("""SELECT user_id, t.upvotes, t.downvotes,
                        (CASE WHEN to_timestamp({})::timestamp <= last_activity + INTERVAL '1 year' THEN TRUE 
                                ELSE FALSE END) as active
                        FROM trolls t JOIN users USING(user_id)
                        ORDER BY t.downvotes-t.upvotes DESC, user_id;""".format(args['timestamp']))
        rows = cur.fetchall()
        cur.close()
        return True, rows
