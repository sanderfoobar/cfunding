import peewee as pw


class EnumField(pw.IntegerField):
    def __init__(self, choices, *args, **kwargs):
        super(pw.IntegerField, self).__init__(*args, **kwargs)
        self.choices = choices

    def db_value(self, value):
        if isinstance(value, int):
            return value
        return value.value

    def python_value(self, value):
        return self.choices(value)
