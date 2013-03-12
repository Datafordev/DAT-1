class InvalidOperation(ValueError):
    """Error while executing an expression.
    """
    def __init__(self, message, fix=None, select=None):
        self.fix = fix          # Fixed expression
        self.select = select    # What to select in the fixed expression
        ValueError.__init__(self, message)


class OperationWarning(UserWarning):
    pass


def is_operator(op_name):
    return op_name in iter('+-*/')


from dat.operations.execution import perform_operation
