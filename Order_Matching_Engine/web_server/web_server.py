from flask import Flask, render_template, request, jsonify
import requests
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web_server")

# Store orders temporarily (This should be replaced with a database)
orders = []

@app.route('/')
def index():
    return render_template('index.html')

# API endpoint to place an order (frontend calls this)
@app.route('/order', methods=['POST'])
def place_order():
    try:
        data = request.get_json()
        price = data.get('price')
        quantity = data.get('quantity')
        side = data.get('side')
        order_type = data.get('type')

        logger.info(f"Tried to send order of type: {order_type}, price: {price}, quantity: {quantity}, side: {side}")
        if order_type == "market":
            if not quantity or not side:
                return jsonify({"error": "Missing quantity or side for market order"}), 400
        else:
            if not price or not quantity or not side:
                return jsonify({"error": "Missing required fields for limit order"}), 400

        order = {"type": order_type, "quantity": quantity, "price": price, "side": side, "user": "LUKE_BARRY"}
        orders.append(order)  # Store the order (temporary)

        # Send order to QUIC client
        client_url = "http://quic-client:6060/api/order"  # Internal Docker network
        response = requests.post(client_url, json=order)

        if response.status_code == 200:
            return jsonify({"success": True, "order": order}), 200
        else:
            return jsonify({"error": "Failed to forward order to client"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=6060)
