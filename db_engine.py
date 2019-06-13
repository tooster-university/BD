import psycopg2
from enum import Enum
from decimal import Decimal


# command execution modes
class Mode(Enum):
    NONE = 0   # can be run without authentication
    USER = 1   # can be run by users with authentication, creates user if doesn't exist
    LEADER = 2 # can be run only by eader with authentication

class Command():
    # binding is a function bound to this command
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
            if ('timestamp' not in args  # not timed command
            or self.engine.timestamp is None  # first timed command
            or args['timestamp'] > self.engine.timestamp):
                if self.engine.__db_auth__(self.mode, args):
                    success, data = self.binding(args)
        except Exception as e:  # all exceptions are caught and status remains failed
            if self.engine.verbose:
                retval['debug'] = str(e)

        if not success:
            retval['status'] = 'ERROR'
        else:
            retval['status'] = 'OK'
            # bump timestamp on success
            if 'timestamp' in args:
                self.engine.timestamp = args['timestamp']
            if data is not None:
                retval['data'] = self.__sanitize_types__(data)
        return retval

# creates new DB engine 
class DB_Engine():

    def __init__(self):
        self.connection = None
        self.timestamp = None # represents last timestamp BUT FOR SESSION
        self.commands = {
            "open":     Command(self, Mode.NONE, self.__db_open__),
            "leader":   Command(self, Mode.NONE, self.__db_leader__),
            "support":  Command(self, Mode.USER, lambda args: self.__db_add_action__(+1, args)),
            "protest":  Command(self, Mode.USER, lambda args: self.__db_add_action__(-1, args)),
            "upvote":   Command(self, Mode.USER, lambda args: self.__db_vote__(+1, args)),
            "downvote": Command(self, Mode.USER, lambda args: self.__db_vote__(-1, args)),
            "actions":  Command(self, Mode.LEADER, self.__db_actions__),
            "projects": Command(self, Mode.LEADER, self.__db_projects__),
            "votes":    Command(self, Mode.LEADER, self.__db_votes__),
            "trolls":   Command(self, Mode.NONE, self.__db_trolls__)
        }
        self.init_setup_flag = False
        self.verbose = False

    # returned objects will contain debug: information on status "ERROR"
    def set_verbose(self):
        self.verbose = True

    # switches engine to first-launch mode
    def init_setup(self):
        self.init_setup_flag = True

    #executes given command as specified in API
    def execute_command(self, command):
        for alias in command:  # there is only one key in command
            return self.commands[alias].execute(command[alias])

    # manages authentication, timestamp bumping and creating users for Mode.USER commands
    def __db_auth__(self, mode, auth_data):
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

            # update last activity
            cur.execute("UPDATE users SET last_activity=to_timestamp({})::timestamp WHERE user_id = {};".format(
                auth_data['timestamp'], auth_data['member']))

            cur.close()
            # check permissions
            return mode == Mode.USER or mode == Mode.LEADER and row[0]

    # connects to database
    def __db_open__(self, args):
        self.connection = psycopg2.connect("dbname={} user={} password={}".format(
            args['database'], args['login'], args['password']))
        self.connection.set_session(autocommit=True)

        if self.init_setup_flag:
            cur = self.connection.cursor()
            cur.execute(open("database.sql", "r").read())
            cur.close()
            self.init_setup_flag = False
        return True, None

    # creates leader
    def __db_leader__(self, args):

        cur = self.connection.cursor()
        cur.execute("INSERT INTO users VALUES ({}, crypt('{}', gen_salt('md5')), TRUE, to_timestamp({})::timestamp, 0, 0);".format(
            args['member'], args['password'], args['timestamp']))
        cur.close()
        return True, None

    # creates support if karma > 0, otherwise creates protest
    def __db_add_action__(self, karma, args):
        if 'authority' not in args:  # when authority is ommitted
            args['authority'] = 0

        cur = self.connection.cursor()
        cur.execute("INSERT INTO actions VALUES ({}, {}, {}, {}, {}, 0, 0)".format(
            args['action'], args['project'], args['member'], args['authority'], 'TRUE' if karma > 0 else 'FALSE'))
        cur.close()
        return True, None

    # creates vote for if karme > 0, otherwise creates vote against
    def __db_vote__(self, karma, args):
        cur = self.connection.cursor()
        # nonexisting action results in foreign key violation
        cur.execute("INSERT INTO votes VALUES ({}, {}, {});".format(
            args['member'], args['action'], 'TRUE' if karma > 0 else 'FALSE'))
        cur.close()
        return True, None

    # returns actions with specified criteria
    def __db_actions__(self, args):
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

    # returns projects with specified criteria
    def __db_projects__(self, args):
        authority_subquery = "AND authority_id = {}".format(
            args['authority']) if 'authority' in args else ""
        cur = self.connection.cursor()
        cur.execute("""SELECT DISTINCT project_id, authority_id FROM actions WHERE TRUE {}
                        ORDER BY project_id;""".format(
            authority_subquery))
        rows = cur.fetchall()
        cur.close()
        return True, rows

    # returns votes summary with specified criteria
    def __db_votes__(self, args):
        action_subquery = "AND action_id = {}".format(
            args['action']) if 'action' in args else ""
        project_subquery = "AND project_id = {}".format(
            args['project']) if 'project' in args else ""
        cur = self.connection.cursor()
        cur.execute("""
            WITH votes_full AS (
                SELECT v.user_id, action_id, project_id, is_upvote 
                FROM votes v JOIN actions USING (action_id) WHERE TRUE {0} {1})
                    (SELECT user_id, 0 as upvotes, 0 as downvotes FROM users
                        WHERE user_id NOT IN (SELECT user_id FROM votes_full))
                    UNION
                    (SELECT user_id, 
                            COUNT(CASE WHEN is_upvote THEN 1 END) AS upvotes, 
                            COUNT(CASE WHEN NOT is_upvote THEN 1 END) AS downvotes 
                        FROM votes_full WHERE TRUE {0} {1} GROUP BY user_id)
                    ORDER BY user_id;""".format(action_subquery, project_subquery))
        rows = cur.fetchall()
        cur.close()
        return True, rows

    # returns current trolls
    def __db_trolls__(self, args):
        cur = self.connection.cursor()
        cur.execute("""SELECT user_id, t.upvotes, t.downvotes,
                        (CASE WHEN to_timestamp({})::timestamp <= last_activity + INTERVAL '1 year' THEN TRUE 
                                ELSE FALSE END) as active
                        FROM trolls t JOIN users USING(user_id)
                        ORDER BY t.downvotes-t.upvotes DESC, user_id;""".format(args['timestamp']))
        rows = cur.fetchall()
        cur.close()
        return True, rows
