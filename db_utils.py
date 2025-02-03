import mysql.connector
from mysql.connector import Error
from flask import current_app


def create_connection():
    """
    Establish a connection to the MySQL database using configurations defined in the app.
    """
    try:
        connection = mysql.connector.connect(
            host=current_app.config['DB_HOST'],
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            database=current_app.config['DB_NAME']
        )
        return connection
    except Error as e:
        print(f"Error connecting to the database: {e}")
        return None


def execute_query(query, params=None):
    """
    Execute a SELECT query and fetch results.

    Args:
        query (str): The SQL query to execute.
        params (tuple): Optional query parameters.

    Returns:
        list: Query results as a list of dictionaries.
    """
    connection = create_connection()
    if not connection:
        return []

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params or ())
        result = cursor.fetchall()
        return result
    except Error as e:
        print(f"Error executing query: {e}")
        return []
    finally:
        if connection:
            connection.close()


def execute_update(query, params=None):
    """
    Execute an INSERT, UPDATE, or DELETE query.

    Args:
        query (str): The SQL query to execute.
        params (tuple): Optional query parameters.
    """
    connection = create_connection()
    if not connection:
        return False

    try:
        cursor = connection.cursor()
        cursor.execute(query, params or ())
        connection.commit()
        return True
    except Error as e:
        print(f"Error executing update: {e}")
        return False
    finally:
        if connection:
            connection.close()


def fetch_configuration(config_name):
    """
    Fetch a configuration value by its name.

    Args:
        config_name (str): The name of the configuration.

    Returns:
        str: The configuration value, or None if not found.
    """
    query = "SELECT config_value FROM configurations WHERE config_name=%s"
    result = execute_query(query, (config_name,))
    return result[0]['config_value'] if result else None


def update_configuration(config_name, config_value):
    """
    Insert or update a configuration value.

    Args:
        config_name (str): The name of the configuration.
        config_value (str): The new value for the configuration.
    """
    try:
        # First try to update existing record
        update_query = """
            UPDATE configurations 
            SET config_value = %s 
            WHERE config_name = %s
        """
        rows_affected = execute_update(update_query, (config_value, config_name))
        
        # If no rows were updated, insert new record
        if rows_affected == 0:
            insert_query = """
                INSERT INTO configurations (config_name, config_value)
                VALUES (%s, %s)
            """
            execute_update(insert_query, (config_name, config_value))
        
        print(f"Updated configuration: {config_name} = {config_value}")  # Debug print
    except Exception as e:
        print(f"Error updating configuration {config_name}: {str(e)}")  # Debug print
        raise
