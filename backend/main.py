from tools.db import get_db_connection

def main():
    name = "king-pizza"

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT into tenants (name)
                    VALUES(%s)
                    RETURNING id
                """, (name,)
            )
            return cur.fetchall()





if __name__ == "__main__":
    row = main()
    print(row)
