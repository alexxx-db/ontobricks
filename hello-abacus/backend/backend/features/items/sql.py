LIST_ITEMS = "SELECT id, name FROM app_data.items ORDER BY id DESC LIMIT %(limit)s"
CREATE_ITEM = (
    "INSERT INTO app_data.items (name, created_by) VALUES (%(name)s, %(created_by)s) "
    "RETURNING id, name"
)
