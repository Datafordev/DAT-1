import re
from tdparser import Lexer, Token, ParserError

from dat import variable_format
from dat.utils import iswhitespace


class InvalidExpression(ValueError):
    """Error while parsing an expression.
    """
    def __init__(self, message, fix=None, select=None):
        self.fix = fix          # Fixed expression
        self.select = select    # What to select in the fixed expression
        ValueError.__init__(self, message)


SYMBOL = 1
NUMBER = 2
OP = 3


class Symbol(Token):
    regexp = variable_format
    def __init__(self, text):
        self.value = text
        Token.__init__(self, text)

    def nud(self, context):
        return (SYMBOL, self.value)


class Integer(Token):
    regexp = r'\d+'

    def __init__(self, text):
        self.value = int(text)
        Token.__init__(self, text)

    def nud(self, context):
        return (NUMBER, self.value)


class Addition(Token):
    regexp = r'\+'
    lbp = 20 # Precedence

    def led(self, left, context):
        right = context.expression(self.lbp)
        return (OP, '+', left, right)


class Substraction(Token):
    regexp = r'-'
    lbp = 20 # Precedence: same as addition

    def led(self, left, context):
        # Binary operator
        right = context.expression(self.lbp)
        return (OP, '-', left, right)

    def nud(self, context):
        # Unary operator
        expr = context.expression(self.lbp)
        if expr[0] == NUMBER:
            return (NUMBER, -expr[1])
        else:
            return (OP, '_', expr)


class Multiplication(Token):
    regexp = r'\*'
    lbp = 30 # Precedence: higher than addition

    def led(self, left, context):
        right = context.expression(self.lbp)
        return (OP, '*', left, right)


class Division(Token):
    regexp = r'/'
    lbp = 30 # Precedence: same as multiplication

    def led(self, left, context):
        right = context.expression(self.lbp)
        return (OP, '/', left, right)


class LeftParen(Token):
    regexp = r'\('
    lbp = 100 # Left binding power: highest
    rbp = 10 # Right binding power: lowest

    def led(self, left, context):
        # Binary operator: corresponds to the function call contruct, as in
        # 2 * abc(7, 31) + 18
        params = []
        if left[0] != SYMBOL:
            raise InvalidExpression("Function call syntax only allowed on "
                                    "symbols")
        if not isinstance(context.current_token, RightParen):
            while True:
                params.append(context.expression(self.rbp))
                if not isinstance(context.current_token, Comma):
                    break
                context.consume(expect_class=Comma)
        context.consume(RightParen)
        return (OP, left) + tuple(params)

    def nud(self, context):
        # Unary operator: corresponds to the parenthesized construct, as in
        # 2 * (3 + 1)

        # Fetch the next expression
        expr = context.expression()
        # Eat the next token, that should be a ')'
        context.consume(expect_class=RightParen)
        return expr


class RightParen(Token):
    regexp = r'\)'


class Comma(Token):
    regexp = r','


lexer = Lexer()
lexer.register_tokens(
        Symbol, Integer,
        Addition, Substraction, Multiplication, Division,
        LeftParen, RightParen, Comma)


_variable_format = re.compile('^' + variable_format + '$')

def parse_expression(expression):
    equal = expression.find('=')
    if equal == -1:
        raise InvalidExpression("Missing target variable name",
                                "new_var = %s" % expression,
                                (0, 7))
    else:
        target = expression[:equal].strip()
        if not _variable_format.match(target):
            right = equal
            if right > 0 and expression[right-1] == ' ':
                right -= 1
            if iswhitespace(expression[0:right]):
                raise InvalidExpression("Missing target variable name",
                                        "new_var %s" % expression.lstrip(),
                                        (0, 7))
            else:
                raise InvalidExpression("Invalid target variable name",
                                        None,
                                        (0, right))
        expression = expression[equal+1:]
    try:
        return target, lexer.parse(expression)
    except (ParserError, ValueError):
        raise InvalidExpression("Error while parsing expression")


def perform_operation(controller, expression):
    """Perform a variable operation from the given string.
    """
    # First, parse the expressions
    target, expr_tree = parse_expression(expression)
    # TODO-dat : execute operation

def is_operator(op_name):
    return op_name in iter('+-*/')
