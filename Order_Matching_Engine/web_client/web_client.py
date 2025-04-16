from flask import Flask, render_template, request, jsonify
import requests
import logging
import os

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web_server")

# Get configuration from environment variables
CLIENT_HOST = os.environ.get("CLIENT_HOST", "quic-client")
CLIENT_PORT = os.environ.get("CLIENT_PORT", "6060")
CLIENT_URL = f"http://{CLIENT_HOST}:{CLIENT_PORT}"
USER_ID = os.environ.get("USER_ID", "TRADER1")

logger.info(f"Web server starting with CLIENT_URL: {CLIENT_URL}, USER_ID: {USER_ID}")

# Store orders temporarily (This should be replaced with a database)
orders = []

@app.route('/')
def index():
    # Pass USER_ID to the template
    return render_template('index.html', user_id=USER_ID)

@app.route('/api/orderbook', methods=['GET'])
def get_orderbook():
    try:
        # Forward request to QUIC client
        response = requests.get(f"{CLIENT_URL}/api/orderbook")
        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            return jsonify({"error": "Failed to fetch orderbook"}), 500
    except Exception as e:
        logger.error(f"Error fetching orderbook: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/orders/<user_id>', methods=['GET'])
def get_user_orders(user_id):
    try:
        # Forward request to QUIC client
        response = requests.get(f"{CLIENT_URL}/api/orders/{user_id}")
        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            return jsonify({"error": "Failed to fetch user orders"}), 500
    except Exception as e:
        logger.error(f"Error fetching user orders: {e}")
        return jsonify({"error": str(e)}), 500

# API endpoint to place an order (frontend calls this)
@app.route('/api/order', methods=['POST'])
def place_order():
    """Place an order via the QUIC client."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Validate required fields
        required_fields = ["type", "side", "quantity"]
        if data.get("type") == "limit":
            required_fields.append("price")
            
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        # Convert numeric strings to numbers
        if "price" in data:
            data["price"] = float(data["price"])
        data["quantity"] = int(data["quantity"])
         
        # Validate for limit orders
        if data.get("type") == "limit":
            if data["quantity"] == 0:
                return jsonify({"error": "Order quantity must not be 0 for limit orders"}), 400
            if data["price"] == 0:
                return jsonify({"error": "Order price must not be 0 for limit orders"}), 400
        
        # Add user ID
        data["user"] = USER_ID

        logger.info(f"Trying to send order of type: {data['type']}, price: {data.get('price')}, quantity: {data['quantity']}, side: {data['side']}")
        
        # Forward the order to the QUIC client
        response = requests.post(
            f"{CLIENT_URL}/api/order",
            json=data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            return jsonify({"message": "Order placed successfully"}), 200
        else:
            return jsonify({"error": "Failed to place order"}), response.status_code

    except Exception as e:
        logger.error(f"Error placing order: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/order/<order_id>', methods=['DELETE'])
def cancel_order(order_id):
    """Cancel a specific order."""
    try:
        # Send cancel request to the client
        response = requests.delete(f"{CLIENT_URL}/api/order/{order_id}")
        
        if response.status_code != 200:
            return jsonify({"error": "Failed to cancel order"}), response.status_code
            
        return jsonify({"message": "Cancel request sent"}), 200
        
    except Exception as e:
        logger.error(f"Error cancelling order: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/order/<order_id>', methods=['DELETE'])
def cancel_order_legacy(order_id):
    try:
        # Send cancel request to QUIC client
        client_url = f"{CLIENT_URL}/api/order/{order_id}"
        response = requests.delete(client_url)

        if response.status_code == 200:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Failed to cancel order"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=6060)
