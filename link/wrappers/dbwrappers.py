from link import Wrapper
from link.utils import list_to_dataframe

class DBCursorWrapper(Wrapper):
    """
    Wraps a select and makes it easier to tranform the data
    """
    def __init__(self, cursor, query = None, wrap_name = None):
        self.cursor = cursor
        self._data = None
        self._columns = None
        self.query = query
        super(DBCursorWrapper, self).__init__(wrap_name, cursor)
    
    @property
    def columns(self):
        if not self._columns:
            self._columns = [x[0].lower() for x in self.cursor.description]
        return self._columns
    
    @property
    def data(self):
        if not self._data:
           self._data = self.cursor.fetchall() 
        return self._data

    def as_dataframe(self):
        try:
            from pandas import DataFrame
        except:
            raise Exception("pandas required to select dataframe. Please install"  + 
                            "sudo easy_install pandas")
        columns = self.columns
        #check to see if they have duplicate column names
        if len(columns)>len(set(columns)):
            raise Exception("Cannot have duplicate column names " +
                            "in your query %s, please rename" % columns)
        return list_to_dataframe(self.data, columns) 
    
    def _create_dict(self, row):
        return dict(zip(self.columns, row)) 

    def as_dict(self):
        return map(self._create_dict,self.data)

    def __iter__(self):
        return self.data.__iter__()
    
    def __call__(self, query = None):
        """
        Creates a cursor and executes the query for you
        """
        if not query:
            query = self.query
        self.cursor.execute(query)
        return self

class DBConnectionWrapper(Wrapper):
    """
    wraps a database connection and extends the functionality
    to do tasks like put queries into dataframes
    """
    def __init__(self, wrap_name = None, chunked=False, **kwargs):
        
        if kwargs:
            self.__dict__.update(kwargs)

        #get the connection and pass it to wrapper os the wrapped object
        self.chunked = chunked
        self._chunks = None
        connection = self.create_connection()
        super(DBConnectionWrapper, self).__init__(wrap_name, connection)
    
    @property
    def chunks(self):
        return self._chunks

    def chunk(self, chunk_name):
        """
        this is the default lookup of one of the database chunks
        """
        if self.chunks == None:
           raise Exception('This is not a chunked connection ') 
        
        return self.chunks.get(chunk_name)

    def execute(self, query):
        """
        Creates a cursor and executes the query for you
        """
        cursor = self._wrapped.cursor()
        cursor.execute(query)
        return cursor

    #TODO: Add in the ability to pass in params and also index 
    def select_dataframe(self, query):
        """
        Select everything into a datafrome with the column names
        being the names of the colums in the dataframe
        """
        try:
            from pandas import DataFrame
        except:
            raise Exception("pandas required to select dataframe. Please install"  + 
                            "sudo easy_install pandas")

        cursor = self.execute(query)
        data = cursor.fetchall()
        columns = [x[0].lower() for x in cursor.description]
        
        #check to see if they have duplicate column names
        if len(columns)>len(set(columns)):
            raise Exception("Cannot have duplicate column names " +
                            "in your query %s, please rename" % columns)
        return list_to_dataframe(data, columns) 
    
    def select(self, query=None, chunk_name = None):
        """
        Run a select and just return everything. If you have pandas installed it
        is better to use select_dataframe if you want to do data manipulation
        on the results
        """
        cursor = None
        if chunk_name:
            #look up the db chunk that you want to read from
            cursor = self.chunk(chunk_name).cursor()
        else:
            cursor = self._wrapped.cursor()

        if not cursor:
            raise Exception("no cursor found")

        return DBCursorWrapper(cursor, query)()
 
    def create_connection(self):
        """
        Override this function to create a depending on the type
        of database

        :returns: connection to the database you want to use
        """
        pass


class SqliteDBConnectionWrapper(DBConnectionWrapper):
    """
    A connection wrapper for a sqlite database
    """
    def __init__(self, wrap_name=None, path=None, chunked = False, 
                create_db = True):
        """
        A connection for a SqlLiteDb.  Requires that sqlite3 is
        installed into python

        :param path: Path to the sqllite db.  
        :param create_db: if True Create if it does not exist in the 
                          file system.  Otherwise throw an error
        :param chunked: True if this in a path to a chunked sqlitedb
        """
        self.create_db = create_db

        if not path:
            raise Exception("Path Required to create a sqllite connection")
        super(SqliteDBConnectionWrapper, self).__init__(wrap_name=wrap_name, 
                                                  path=path, chunked = chunked)

    def create_connection(self):
        """
        Override the create_connection from the DbConnectionWrapper
        class which get's called in it's initializer
        """
        # if we are chunking and this is not a db then don't try to make a
        # connection
        if self.chunked and not self.path.endswith('.db'):
            return None

        return self._connection_from_path(self.path)
    
    def _connection_from_path(self, path):
        import sqlite3
        db = sqlite3.connect(path)
        return db

    @property
    def chunks(self):
        """
        For sqlite we are chunking by making many files that are of smaller size 
        This makes it easy to distribute out certain parts of it. Directory
        structure looks like this::

            test_db.db --> sqlitedb
            test_db/
                my_chunk.db --> another small chunk

        """
        if self._chunks:
            return self._chunks

        if  self.chunked:
            self._chunks = self._get_chunks()
            return self._chunks

        raise Exception("This database is not chunked")

    def chunk(self, chunk_name):
        """
        Get a chunk and if its not connected yet then connect it
        """
        chunk = self.chunks.get(chunk_name)
        if chunk:
            #if its a string then create the connection and put it in _chunks
            if isinstance(chunk,str) or isinstance(chunk,unicode):
                chunk = self._connection_from_path(chunk)
                self._chunks[chunk_name] = chunk
            return chunk  

        raise Exception("there is no chunk")
    
    def _get_chunks(self):
        """
        creates connections for each chunk in the set of them
        """
        import os
        dir = self.path
        #rstrip will remove too much if you you path is /path/test_db.db
        if dir.endswith('.db'):
            dir = dir[:-3]

        dir = dir.rstrip('/')
        dbs = os.listdir(dir)

        return dict([
            (name, '%s/%s' % (dir, name))
             for name in dbs
            ]
        )
    
    def __call__(self):
        """
        Run's the command line sqlite application
        """
        self.run_command('sqlite3 %s' % self.path)

    
class MysqlDBConnectionWrapper(DBConnectionWrapper):

    def __init__(self, wrap_name=None, user=None, password=None, 
                 host=None, database=None):
        """
        A connection for a Mysql Database.  Requires that
        MySQLdb is installed

        :param user: your user name for that database 
        :param password: Your password to the database
        :param host: host name or ip of the database server
        :param database: name of the database on that server 
        """
        self.user = user
        self.password = password
        self.host = host
        self.database = database
        super(MysqlDBConnectionWrapper, self).__init__(wrap_name=wrap_name)

    def create_connection(self):
        """
        Override the create_connection from the DbConnectionWrapper
        class which get's called in it's initializer
        """
        import MySQLdb.connections
        import MySQLdb.converters
        import MySQLdb
        
        # make it so that it uses floats instead of those Decimal objects
        # these are really slow when trying to load into numpy arrays and 
        # into pandas
        conv = MySQLdb.converters.conversions.copy()
        conv[MySQLdb.constants.FIELD_TYPE.DECIMAL] = float
        conv[MySQLdb.constants.FIELD_TYPE.NEWDECIMAL] = float
        conn = MySQLdb.connect(host=self.host, user=self.user, 
                               db=self.database, passwd=self.password,
                               conv=conv)
        return conn

    def __call__(self, query = None, outfile= None):
        """
        Create a shell connection to this mysql instance
        """
        cmd = 'mysql -A -u %s -p%s -h %s %s' % (self.user, self.password,
                                                     self.host, self.database)
        self.run_command(cmd)

