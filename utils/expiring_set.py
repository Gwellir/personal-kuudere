from time import time


class ExpiringSet:
    def __init__(self, default_max_age: int = 3600):
        assert default_max_age > 0
        self.container = {}
        self.max_age = default_max_age

    def __contains__(self, item) -> bool:
        if item not in self.container:
            return False
        if self.container[item] < time():
            del self.container[item]
            return False

        return True

    def add(self, item, custom_max_age: int = None):
        assert custom_max_age > 0
        max_age = self.max_age if not custom_max_age else custom_max_age
        self.container[item] = time() + max_age
