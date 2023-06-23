from datetime import datetime
from flask import Flask, request, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import login_required, LoginManager, UserMixin, login_user, current_user, logout_user
from flasgger import Swagger
from flasgger.utils import swag_from

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///orders.db'
app.secret_key = 'super-secret-key'
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
swagger = Swagger(app)


class Order(db.Model):
    __tablename__ = 'order'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    price = db.Column(db.Float)
    product_name = db.Column(db.String(80))
    bill_created_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default="received")

    def __init__(self, product_id, product_name, price, status="received"):
        self.product_id = product_id
        self.price = price
        self.product_name = product_name
        self.status = status

    @property
    def name(self):
        return self.product.name


class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    price = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    orders = db.relationship('Order', backref='product', lazy=True)


class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    password = db.Column(db.String(128))
    role = db.Column(db.String(64))

    def __init__(self, username, password, role):
        self.username = username
        self.password = password
        self.role = role

    def set_password(self, password):
        self.password = password

    def check_password(self, password):
        return self.password == password


@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    return user


with app.app_context():
    db.create_all()


@app.before_request
def create_initial_users():
    with app.app_context():
        db.create_all()

        existing_users = User.query.all()
        if existing_users:
            return

        accountant = User(username='accountant', password='accountant123', role='accountant')
        db.session.add(accountant)

        cashier = User(username='cashier', password='cashier123', role='cashier')
        cashier.set_password('cashier123')
        db.session.add(cashier)

        sales_assistant = User(username='sales assistant', password='sales123', role='sales assistant')
        sales_assistant.set_password('sales123')
        db.session.add(sales_assistant)

        products = [
            {'name': 'Product 1', 'price': 10.0},
            {'name': 'Product 2', 'price': 20.0},
            {'name': 'Product 3', 'price': 30.0},
            {'name': 'Product 4', 'price': 40.0}
        ]
        for product_data in products:
            product = Product(name=product_data['name'], price=product_data['price'])
            db.session.add(product)

        db.session.commit()


@app.route('/users')
def user_list():
    users = User.query.all()

    result = []
    for user in users:
        result.append({
            'id': user.id,
            'username': user.username,
            'role': user.role,
            'password': user.password
        })

    return jsonify({'users': result})


@app.route('/orders', methods=['PUT'])
@login_required
@swag_from({
    'tags': ['Orders'],
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'product_name': {
                        'type': 'string'
                    }
                }
            }
        }
    ],
    'responses': {
        201: {
            'description': 'Order added successfully',
            'schema': {
                'type': 'object',
                'properties': {
                    'message': {
                        'type': 'string'
                    },
                    'order': {
                        '$ref': '#/definitions/Order'
                    }
                }
            }
        },
        400: {
            'description': 'Invalid request',
            'schema': {
                'type': 'object',
                'properties': {
                    'message': {
                        'type': 'string'
                    }
                }
            }
        },
        403: {
            'description': 'Forbidden',
            'schema': {
                'type': 'object',
                'properties': {
                    'message': {
                        'type': 'string'
                    }
                }
            }
        },
        404: {
            'description': 'Product not found',
            'schema': {
                'type': 'object',
                'properties': {
                    'message': {
                        'type': 'string'
                    }
                }
            }
        }
    }
})
def add_order():
    if current_user.role not in ['cashier', 'sales assistant', 'accountant']:
        abort(403)
    data = request.get_json()
    product_name = data.get('product_name')

    if not product_name:
        abort(400, 'Invalid request. Please provide product name.')

    product = Product.query.filter_by(name=product_name).first()

    if not product:
        abort(404, 'Product not found.')

    existing_order = Order.query.filter_by(product_id=product.id).first()
    if existing_order:
        existing_order.price = product.price
        db.session.commit()
        return {
                   'message': 'Order updated successfully',
                   'order': {
                       'id': existing_order.id,
                       'product_name': product.name,
                       'product_price': existing_order.price,
                       'status': existing_order.status,
                       'created_at': existing_order.created_at
                   }
               }, 200

    new_order = Order(product_id=product.id, product_name=product.name, price=product.price)
    db.session.add(new_order)
    db.session.commit()

    return {
               'message': 'Order added successfully',
               'order': {
                   'id': new_order.id,
                   'product_name': new_order.product.name,
                   'product_price': new_order.price,
                   'status': new_order.status,
                   'created_at': new_order.created_at
               }
           }, 201


@app.route('/orders', methods=['GET'])
@login_required
def get_orders():
    """
    Retrieve orders based on optional start_date and end_date parameters.
    ---
    parameters:
      - name: start_date
        in: query
        type: string
        description: Start date for filtering orders (YYYY-MM-DD format)
      - name: end_date
        in: query
        type: string
        description: End date for filtering orders (YYYY-MM-DD format)
    responses:
      200:
        description: Successful response
        schema:
          properties:
            orders:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  name:
                    type: string
                  price:
                    type: number
                  status:
                    type: string
                  created at:
                    type: string
                  bill created at:
                    type: string
    """
    if current_user.role not in ['accountant']:
        abort(403)

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    query = Order.query

    if start_date_str and end_date_str:
        date_format = '%Y-%m-%d'
        start_date = datetime.strptime(start_date_str, date_format)
        end_date = datetime.strptime(end_date_str, date_format)

        query = query.filter(Order.created_at.between(start_date, end_date))

    orders = query.all()

    result = []
    for order in orders:
        result.append({
            'id': order.id,
            'name': order.name,
            'price': order.price,
            'status': order.status,
            'created at': order.created_at,
            'bill created at': order.bill_created_at
        })

    return {'orders': result}


@app.route('/orders/<int:order_id>', methods=['GET'])
@login_required
@swag_from({
    'parameters': [
        {
            'name': 'order_id',
            'in': 'path',
            'type': 'integer',
            'required': True,
            'description': 'The ID of the order'
        }
    ],
    'responses': {
        200: {
            'description': 'Order details',
            'schema': {
                'id': 'integer',
                'name': 'string',
                'status': 'string',
                'price': 'float',
                'created_at': 'string'
            }
        },
        403: {
            'description': 'Forbidden'
        },
        404: {
            'description': 'Order not found'
        }
    }
})
def get_order(order_id):
    """
    Get details of a specific order.
    """
    if current_user.role not in ['sales assistant', 'accountant']:
        abort(403)

    order = Order.query.get(order_id)

    if not order:
        return 'Order not found', 404

    creation_date = order.created_at
    current_date = datetime.utcnow()
    delta = current_date - creation_date

    if delta.days > 30:
        discount = 0.2  # 20% discount
        discounted_price = order.price * (1 - discount)
        result = {
            'id': order.id,
            'name': order.name,
            'status': order.status,
            'price': discounted_price,
            'created_at': order.created_at
        }
    else:
        result = {
            'id': order.id,
            'name': order.name,
            'status': order.status,
            'price': order.price,
            'created_at': order.created_at
        }

    return result, 200


@app.route('/orders/<int:order_id>', methods=['PUT'])
@login_required
@swag_from({
    'parameters': [
        {
            'name': 'order_id',
            'in': 'path',
            'type': 'integer',
            'required': True,
            'description': 'The ID of the order'
        },
        {
            'name': 'status',
            'in': 'body',
            'type': 'string',
            'required': True,
            'description': 'The updated status of the order'
        }
    ],
    'responses': {
        200: {
            'description': 'Order updated successfully',
            'schema': {
                'id': 'integer',
                'product_id': 'integer',
                'product_name': 'string',
                'price': 'float',
                'status': 'string',
                'created_at': 'string'
            }
        },
        400: {
            'description': 'Invalid request'
        },
        403: {
            'description': 'Forbidden'
        },
        404: {
            'description': 'Order not found'
        }
    }
})
def update_order(order_id):
    """
    Update the status of an order.
    """
    order = Order.query.get(order_id)

    if not order:
        abort(404, 'Order not found')

    new_status = request.json.get('status')
    if not new_status:
        abort(400, 'Invalid request')

    order.status = new_status
    db.session.commit()

    updated_order = {
        'id': order.id,
        'product_id': order.product_id,
        'product_name': order.product_name,
        'price': order.price,
        'status': order.status,
        'created_at': order.created_at
    }

    return jsonify(updated_order)


@app.route('/bill/<int:order_id>', methods=['PUT'])
@login_required
@swag_from({
    'parameters': [
        {
            'name': 'order_id',
            'in': 'path',
            'type': 'integer',
            'required': True,
            'description': 'The ID of the order'
        }
    ],
    'responses': {
        200: {
            'description': 'Bill created successfully',
            'schema': {
                'type': 'object',
                'properties': {
                    'message': {
                        'type': 'string',
                        'description': 'Success message'
                    },
                    'order': {
                        'type': 'object',
                        'properties': {
                            'id': {'type': 'integer'},
                            'name': {'type': 'string'},
                            'price': {'type': 'float'},
                            'status': {'type': 'string'},
                            'created_at': {'type': 'string', 'format': 'date-time'},
                            'bill_created_at': {'type': 'string', 'format': 'date-time'}
                        }
                    }
                }
            }
        },
        403: {
            'description': 'Forbidden'
        },
        404: {
            'description': 'Order not found'
        }
    }
})
def bill_created(order_id):
    """
    Create a bill for an order.
    """
    if current_user.role not in ['accountant', 'cashier']:
        abort(403)
    order = Order.query.get(order_id)

    if not order:
        return 'Order not found', 404
    order.bill_created_at = datetime.utcnow()  # Записываем текущую дату и время в поле bill_created_at
    db.session.commit()

    return {
        'message': 'Bill created successfully',
        'order': {
            'id': order.id,
            'name': order.name,
            'price': order.price,
            'status': order.status,
            'created_at': order.created_at,
            'bill_created_at': order.bill_created_at
        }
    }, 200


@app.route('/login', methods=['POST'])
@swag_from({
    'parameters': [
        {
            'name': 'username',
            'in': 'body',
            'type': 'string',
            'required': True,
            'description': 'The username'
        },
        {
            'name': 'password',
            'in': 'body',
            'type': 'string',
            'required': True,
            'description': 'The password'
        }
    ],
    'responses': {
        200: {
            'description': 'User logged in successfully'
        },
        401: {
            'description': 'Unauthorized'
        }
    }
})
def login():
    """
    Log in to the application.
    """
    username = request.json.get('username')
    password = request.json.get('password')

    if not username or not password:
        abort(401, 'Unauthorized')

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        abort(401, 'Unauthorized')

    login_user(user)

    return jsonify({'message': 'User logged in successfully'})


@app.route('/logout', methods=['GET'])
@login_required
@swag_from({
    'responses': {
        200: {
            'description': 'User logged out successfully'
        }
    }
})
def logout():
    """
    Log out of the application.
    """
    logout_user()
    return jsonify({'message': 'User logged out successfully'})


if __name__ == '__main__':
    app.run()
