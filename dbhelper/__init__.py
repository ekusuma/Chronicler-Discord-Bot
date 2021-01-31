import mysql.connector
from mysql.connector import Error


################################################################################
# Basic setup functions
################################################################################

def query(conn, query, verbose=True):
    cursor = conn.cursor()
    try:
        cursor.execute(query)
        conn.commit()
        if verbose:
            print('Query successful')
        return 0
    except Error as err:
        print('Error: {}'.format(err))
        return 1

def read_query(conn, query):
    result = None
    cursor = conn.cursor()
    try:
        cursor.execute(query)
        result = cursor.fetchall()
    except Error as err:
        print('Error: {}'.format(err))
    return result

def create_srv_conn(host_name, user_name, user_pw, dbname):
    conn = None
    try:
        conn = mysql.connector.connect(
            host=host_name,
            user=user_name,
            passwd=user_pw
        )
        retval = query(conn, "USE {};".format(dbname), False)
        if retval != 0:
            print('Cannot establish MySQL DB connection.')
            return None
        print('Established MySQL DB connection.')
        print('Database changed to {}'.format(dbname))
    except Error as err:
        print('Error: {}'.format(err))
    return conn


################################################################################
# Table management
################################################################################

def create_table(conn, table, columns):
    q = 'CREATE TABLE {} ({});'.format(table, columns)
    retval = query(conn, q, False)
    if retval == 0:
        print('Created table {}'.format(table))
    else:
        print('Cannot create table {}'.format(table))
    return retval

def drop_table(conn, table):
    q = 'DROP TABLE {};'.format(table)
    retval = query(conn, q, False)
    if retval == 0:
        print('Dropped table {}'.format(table))
    else:
        print('Cannot drop table {}'.format(table))
    return retval


################################################################################
# Entry management
################################################################################

def insert(conn, table, values):
    q = 'INSERT INTO {} VALUES ({});'.format(table, values)
    retval = query(conn, q, False)
    if retval == 0:
        print('Inserted entry into {}'.format(table))
    else:
        print('Cannot insert into {}'.format(table))
    return retval

def insert_partial(conn, table, columns, values):
    q = 'INSERT INTO {} ({}) VALUES ({});'.format(table, columns, values)
    retval = query(conn, q, False)
    if retval == 0:
        print('Inserted entry into {}'.format(table))
    else:
        print('Cannot insert into {}'.format(table))
    return retval

def delete(conn, table, where):
    if where == None:
        q = 'DELETE FROM {};'.format(table)
    else:
        q = 'DELETE FROM {} WHERE {};'.format(table, where)
    retval = query(conn, q, False)
    if retval == 0:
        print('Deleted entry from {}'.format(table))
    else:
        print('Cannot insert from {}'.format(table))
    return retval


################################################################################
# Reading functions
################################################################################

def select(conn, table, columns, where):
    if where == None:
        q = 'SELECT {} FROM {};'.format(columns, table)
    else:
        q = 'SELECT {} FROM {} WHERE {};'.format(columns, table, where)
    return read_query(conn, q)
