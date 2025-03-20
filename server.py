from flask import Flask, request, jsonify
from flask_cors import CORS
import hashlib
import json
import time
import sqlite3
import random
import os

# Flask setup
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})

# Metrics file
METRICS_FILE = "pbft_metrics.json"


def log_metrics(latency, tps, energy, success_rate, efficiency):
    """Log performance metrics to a JSON file."""
    data = {"latency": latency, "tps": tps, "energy": energy, "success_rate": success_rate, "efficiency": efficiency}
    if os.path.exists(METRICS_FILE):
        with open(METRICS_FILE, "r+") as file:
            try:
                metrics = json.load(file)
            except json.JSONDecodeError:
                metrics = []
            metrics.append(data)
            file.seek(0)
            json.dump(metrics, file, indent=4)
    else:
        with open(METRICS_FILE, "w") as file:
            json.dump([data], file, indent=4)


class Blockchain:
    def __init__(self):
        self.chain = []
        self.records = []
        self.validators = ["Node A", "Node B", "Node C", "Node D"]
        self.db_init()
        self.load_chain()
        self.start_time = time.time()
        self.tx_count = 0
        self.successful_blocks = 0
        self.attempted_blocks = 0
        self.energy_used = 0  # Reset energy after every block addition

    def db_init(self):
        with sqlite3.connect("blockchain.db") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    records TEXT,
                    previous_hash TEXT
                )
            """)
            conn.commit()

    def validate_record(self, record):
        required_fields = ["patient_id", "medical_data", "doctor_id", "department", "medicine"]
        return all(record.get(field) for field in required_fields)

    def create_candidate_block(self):
        previous_block = self.get_previous_block()
        previous_hash = self.hash(previous_block) if previous_block else "0"
        return {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "records": self.records.copy(),
            "previous_hash": previous_hash
        }

    def add_block(self, candidate_block):
        try:
            with sqlite3.connect("blockchain.db") as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO blocks (timestamp, records, previous_hash) VALUES (?, ?, ?)",
                               (candidate_block["timestamp"], json.dumps(candidate_block["records"]),
                                candidate_block["previous_hash"]))
                conn.commit()
                self.chain.append({
                    "index": cursor.lastrowid,
                    "timestamp": candidate_block["timestamp"],
                    "records": candidate_block["records"],
                    "previous_hash": candidate_block["previous_hash"]
                })
            self.records.clear()
            self.successful_blocks += 1  # Track successful blocks
            self.energy_used = 0  # Reset energy after each block addition
            return True, "Block added successfully!"
        except sqlite3.Error as e:
            return False, str(e)

    def load_chain(self):
        with sqlite3.connect("blockchain.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, timestamp, records, previous_hash FROM blocks ORDER BY id ASC")
            self.chain = [{
                "index": row[0],
                "timestamp": row[1],
                "records": json.loads(row[2]),
                "previous_hash": row[3]
            } for row in cursor.fetchall()]

    def add_record(self, record):
        if self.validate_record(record):
            self.records.append(record)
            self.tx_count += 1
            elapsed_time = time.time() - self.start_time
            tps = self.tx_count / elapsed_time if elapsed_time > 0 else 0
            print(f"PBFT Throughput: {tps:.2f} TPS")
            return True
        return False

    def get_previous_block(self):
        return self.chain[-1] if self.chain else None

    def hash(self, block):
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def pbft_consensus(self):
        if not self.records:
            return False, "No records to validate."

        candidate_block = self.create_candidate_block()
        votes = 0
        required_votes = (2 * len(self.validators)) // 3

        start_time = time.time()
        self.attempted_blocks += 1

        for validator in self.validators:
            if self.validate_candidate_block(candidate_block):
                votes += 1

        end_time = time.time()
        latency = end_time - start_time
        self.energy_used = latency * 20  # Reset and update energy per block
        success_rate = (self.successful_blocks / self.attempted_blocks) * 100 if self.attempted_blocks > 0 else 100
        efficiency = self.tx_count / self.energy_used if self.energy_used > 0 else 0

        print(
            f"PBFT Latency: {latency:.4f} seconds, Estimated Energy: {self.energy_used:.2f} J, Success Rate: {success_rate:.2f}%, Efficiency: {efficiency:.2f}")

        tps = self.tx_count / (time.time() - self.start_time) if (time.time() - self.start_time) > 0 else 0
        log_metrics(latency, tps, self.energy_used, success_rate, efficiency)

        if votes >= required_votes:
            success, message = self.add_block(candidate_block)
            return success, message
        return False, "Consensus failed: Not enough valid votes."

    def validate_candidate_block(self, block):
        return all(self.validate_record(record) for record in block['records'])

# Mock users
users = {
    "doctor": "doctor123",
    "pharmacy": "pharmacy123",
    "department": "dept123"
}

patients = {
    "p001": "patient123",
    "p002": "patient456"
}

blockchain = Blockchain()

@app.route('/')
def serve_frontend():
    return app.send_static_file('index.html')

@app.route('/login', methods=['POST'])
def handle_login():
    data = request.json
    role = data.get('role')

    if role == 'patient':
        if patients.get(data.get('patientId')) == data.get('password'):
            return jsonify({
                "success": True,
                "userType": "patient",
                "patientId": data.get('patientId')
            })
    elif users.get(role) == data.get('password'):
        return jsonify({"success": True, "userType": role})

    return jsonify({"success": False, "message": "Invalid credentials"})

@app.route('/add_record', methods=['POST'])
def handle_add_record():
    data = request.json
    if patients.get(data['patientId']) != data['patientPwd']:
        return jsonify({"success": False, "message": "Invalid patient credentials"})

    record = {
        "patient_id": data['patientId'],
        "medical_data": data['medicalData'],
        "doctor_id": data['doctorId'],
        "department": data['department'],
        "medicine": data['medicine']
    }

    if blockchain.add_record(record):
        return jsonify({"success": True, "message": "Record added successfully!"})
    return jsonify({"success": False, "message": "Invalid record details"})

@app.route('/validate_block', methods=['POST'])
def handle_validate_block():
    success, message = blockchain.pbft_consensus()
    return jsonify({"success": success, "message": message})

@app.route('/get_chain', methods=['POST'])
def handle_get_chain():
    data = request.json
    if patients.get(data.get('patientId')) != data.get('password'):
        return jsonify({"success": False, "message": "Invalid patient credentials"})

    filtered_chain = []
    for block in blockchain.chain:
        filtered_records = [r for r in block['records'] if r['patient_id'] == data['patientId']]
        if filtered_records:
            filtered_block = block.copy()
            filtered_block['records'] = filtered_records
            filtered_chain.append(filtered_block)

    return jsonify({"success": True, "chain": filtered_chain})

if __name__ == '__main__':
    app.run(debug=True)
