from flask import Flask, request, jsonify, send_from_directory
import json
import os
from datetime import datetime

app = Flask(__name__, static_folder='static')

USER_FILE = 'users.json'
LEADERBOARD_FILE = 'leaderboard.json'
INVITE_FILE = 'invites.json'
OLD_LEADERBOARD_FILE = 'old_leaderboard.json'

claimed_rewards = {}  # 简单内存存储今日已领取奖励的用户

def ensure_file(file, default_data):
    if not os.path.exists(file):
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(default_data, f)


ensure_file(USER_FILE, {"users": []})
ensure_file(LEADERBOARD_FILE, {"date": datetime.now().strftime("%Y-%m-%d"), "players": []})
ensure_file(INVITE_FILE, {"date": datetime.now().strftime("%Y-%m-%d"), "invites": {}})

def load_json(file):
    with open(file, 'r', encoding='utf-8') as f:
        return json.load(f)
@app.route('/favicon.png')
def favicon():
    return send_from_directory('static', 'favicon.png')
def save_json(file, data):
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
def load_leaderboard_with_reset():
    today = datetime.now().strftime("%Y-%m-%d")
    data = load_json(LEADERBOARD_FILE)
    if data.get("date") != today:
        # 备份昨日排行榜
        save_json(OLD_LEADERBOARD_FILE, data)
        # 重置
        data = {"date": today, "players": []}
        save_json(LEADERBOARD_FILE, data)
    
    return data


last_checked_date = None

def daily_reset_if_needed():
    global last_checked_date
    today = datetime.now().strftime("%Y-%m-%d")
    if last_checked_date == today:
        return  # 今天已经检查过了

    # 以 leaderboard.json 的日期为准
    data = load_json(LEADERBOARD_FILE)
    if data.get("date") != today:
        # 1. 备份排行榜
        save_json(OLD_LEADERBOARD_FILE, data)
        # 2. 重置排行榜
        save_json(LEADERBOARD_FILE, {"date": today, "players": []})
        # 3. 重置用户 paid 状态
        users = load_json(USER_FILE)
        for u in users['users']:
            u['paid'] = False
        save_json(USER_FILE, users)
        # 4. 重置邀请，无需额外判断
        save_json(INVITE_FILE, {"date": today, "invites": {}})

    last_checked_date = today

# 添加这段在 app 定义后
@app.before_request
def before_any_request():
    daily_reset_if_needed()

def load_invites_with_reset():
    today = datetime.now().strftime("%Y-%m-%d")
    data = load_json(INVITE_FILE)
    if data.get("date") != today:
        data = {"date": today, "invites": {}}
        save_json(INVITE_FILE, data)
    return data

@app.route('/api/register', methods=['POST'])
def register():
    daily_reset_if_needed()
    data = request.json
    users = load_json(USER_FILE)
    if any(u['username'] == data['username'] for u in users['users']):
        return jsonify({"success": False, "message": "Username already registered"})
    users['users'].append({"username": data['username'], "password": data['password'], "paid": False, "is_new": True})
    save_json(USER_FILE, users)
    return jsonify({"success": True, "message": "Registration successful"})

@app.route('/api/login', methods=['POST'])
def login():

    daily_reset_if_needed()
    data = request.json
    users = load_json(USER_FILE)
    for u in users['users']:
        if u['username'] == data['username'] and u['password'] == data['password']:
            return jsonify({"success": True, "message": "Login successful"})
    return jsonify({"success": False, "message": "Incorrect username or password"})

@app.route('/api/check_is_new', methods=['POST'])
def check_is_new():
    daily_reset_if_needed()
    username = request.json.get('username')
    users = load_json(USER_FILE)
    for u in users['users']:
        if u['username'] == username:
            return jsonify({"is_new": u.get('is_new', False)})
    return jsonify({"is_new": False})
@app.route('/api/skip_invite', methods=['POST'])
def skip_invite():
    daily_reset_if_needed()
    username = request.json.get('username')
    users = load_json(USER_FILE)
    for u in users['users']:
        if u['username'] == username:
            u['is_new'] = False
            break
    save_json(USER_FILE, users)
    return jsonify({"success": True})

@app.route('/api/mark_paid', methods=['POST'])
def mark_paid():
    daily_reset_if_needed()
    username = request.json.get('username')
    users = load_json(USER_FILE)

    for u in users['users']:
        if u['username'] == username:
            u['paid'] = True
            save_json(USER_FILE, users)
            return jsonify({"success": True, "message": "Payment marked."})
    return jsonify({"success": False, "message": "User not found."})

@app.route('/api/join', methods=['POST'])
def join():
    daily_reset_if_needed()
    username = request.json.get('username')
    users = load_json(USER_FILE)

    user = next((u for u in users['users'] if u['username'] == username), None)
    if not user:
        return jsonify({"success": False, "message": "User not found."})

    if not user.get('paid', False):
        return jsonify({"success": False, "message": "You have not paid the entry fee."})

    lb = load_leaderboard_with_reset()
    if not any(p['username'] == username for p in lb['players']):
        lb['players'].append({"username": username, "time": 0, "invites": 1})
        save_json(LEADERBOARD_FILE, lb)

    return jsonify({"success": True})


@app.route('/api/generate_invite', methods=['POST'])
def generate_invite():
    daily_reset_if_needed()
    username = request.json.get('username')
    data = load_invites_with_reset()
    invites = data['invites']

    for code, user in invites.items():
        if user == username:
            return jsonify({"invite_code": code})

    invite_code = str(len(invites) + 1).zfill(10)
    invites[invite_code] = username
    save_json(INVITE_FILE, data)
    return jsonify({"invite_code": invite_code})

@app.route('/api/verify_invite', methods=['POST'])
def verify_invite():
    daily_reset_if_needed()
    code = request.json.get('code')
    username = request.json.get('username')

    data = load_invites_with_reset()
    users = load_json(USER_FILE)
    lb = load_leaderboard_with_reset()

    inviter = data['invites'].get(code)
    if not inviter:
        return jsonify({"success": False, "message": "Invalid or used invite code."})

    user_obj = None
    for u in users['users']:
        if u['username'] == username:
            user_obj = u
            break

    if not user_obj:
        return jsonify({"success": False, "message": "User not found."})

    # 这里注意：必须是 is_new == True 才能用邀请码
    if not user_obj.get('is_new', False):
        return jsonify({"success": False, "message": "Invite code can only be used by new players."})

    # 奖励邀请人（邀请人的 invites ×2）
    for p in lb['players']:
        if p['username'] == inviter:
            p['invites'] *= 2
            break

    # 移除邀请码，防止重复使用
    del data['invites'][code]

    # 标记当前用户 is_new = False
    user_obj['is_new'] = False

    # 保存所有变动
    save_json(INVITE_FILE, data)
    save_json(LEADERBOARD_FILE, lb)
    save_json(USER_FILE, users)

    return jsonify({"success": True, "message": "Invite verified. Referrer rewarded."})

@app.route('/api/start_ad', methods=['POST'])
def start_ad():
    username = request.json.get('username')
    lb = load_leaderboard_with_reset()
    now = int(datetime.now().timestamp())  # 当前秒数
    for p in lb['players']:
        if p['username'] == username:
            p['watching_ad'] = True
            p['ad_start_time'] = now  # 新增记录
            break
    save_json(LEADERBOARD_FILE, lb)
    return jsonify({"success": True})

@app.route('/api/end_ad', methods=['POST'])
def end_ad():
    username = request.json.get('username')
    lb = load_leaderboard_with_reset()
    for p in lb['players']:
        if p['username'] == username:
            p['watching_ad'] = False
            p['ad_start_time'] = None
            p['time'] += 1 * p['invites']
            break
    save_json(LEADERBOARD_FILE, lb)
    return jsonify({"success": True})
@app.route('/api/claim_reward_with_email', methods=['POST'])
def claim_reward_with_email():
    daily_reset_if_needed()
    username = request.json.get('username')
    email = request.json.get('email')

    if not username or not email:
        return jsonify({"success": False, "message": "Invalid request."})

    # 查找用户的奖励金额
    reward = 0
    if os.path.exists(OLD_LEADERBOARD_FILE):
        data = load_json(OLD_LEADERBOARD_FILE)
        players = sorted(data.get('players', []), key=lambda x: x['time'], reverse=True)
        prize_pool = round(len(players) * 0.5, 2)

        rank = None
        for idx, p in enumerate(players):
            if p['username'] == username:
                rank = idx + 1
                break

        if rank is not None:
            if rank == 1:
                reward = prize_pool * 0.5
            elif rank == 2:
                reward = prize_pool * 0.25
            elif rank == 3:
                reward = prize_pool * 0.125
            elif 4 <= rank <= 10:
                reward = prize_pool * 0.125 / 7
            reward = round(reward, 2)

    # 保存邮箱+奖励到一个文件
    with open('claimed_emails.txt', 'a', encoding='utf-8') as f:
        f.write(f"{username} : {email} : ${reward}\n")

    # 删除 old_leaderboard 中该用户
    if os.path.exists(OLD_LEADERBOARD_FILE):
        old_data = load_json(OLD_LEADERBOARD_FILE)
        original_count = len(old_data.get('players', []))
        old_data['players'] = [p for p in old_data['players'] if p['username'] != username]
        new_count = len(old_data['players'])

        if original_count != new_count:
            save_json(OLD_LEADERBOARD_FILE, old_data)
        else:
            return jsonify({"success": False, "message": "User not found in old leaderboard."})
    else:
        return jsonify({"success": False, "message": "No old leaderboard found."})

    return jsonify({"success": True, "message": "Reward claimed and email recorded."})
@app.route('/api/claimed_rewards', methods=['GET'])
def claimed_rewards():
    if not os.path.exists('claimed_emails.txt'):
        return jsonify({"list": []})

    entries = []
    with open('claimed_emails.txt', 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split(' : ')
            if len(parts) == 3:
                username, email, reward = parts
                entries.append({
                    "username": username,
                    "email": email,
                    "reward": reward
                })
    return jsonify({"list": entries})


@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    daily_reset_if_needed()
    lb = load_leaderboard_with_reset()
    now = int(datetime.now().timestamp())

    for p in lb['players']:
        if p.get('watching_ad') and p.get('ad_start_time'):
            elapsed = now - p['ad_start_time']
            if elapsed > 60:
                p['watching_ad'] = False
                p['ad_start_time'] = None  # 清除起始时间

    save_json(LEADERBOARD_FILE, lb)
    return jsonify(lb)


@app.route('/api/watch', methods=['POST'])
def watch():
    daily_reset_if_needed()
    username = request.json.get('username')
    lb = load_leaderboard_with_reset()
    for p in lb['players']:
        if p['username'] == username:
            p['time'] += 1 * p['invites']
    save_json(LEADERBOARD_FILE, lb)
    return jsonify({"success": True})

@app.route('/api/exit', methods=['POST'])
def exit_game():

    return jsonify({"success": True, "message": "Exited. You can join later for free"})

@app.route('/api/status', methods=['GET'])
def get_status():
    daily_reset_if_needed()
    lb = load_leaderboard_with_reset()
    players_count = len(lb['players'])
    prize_pool = round(players_count * 0.5, 2)
    return jsonify({"players": players_count, "pool": prize_pool})

# 新增：检查是否支付
@app.route('/api/old_leaderboard', methods=['POST'])
def old_leaderboard():
    daily_reset_if_needed()
    username = request.json.get('username')
    if not os.path.exists(OLD_LEADERBOARD_FILE):
        return jsonify({"success": False, "message": "No previous competition data."})

    data = load_json(OLD_LEADERBOARD_FILE)
    players = sorted(data['players'], key=lambda x: x['time'], reverse=True)
    prize_pool = round(len(players) * 0.5, 2)

    rank = None
    for idx, p in enumerate(players):
        if p['username'] == username:
            rank = idx + 1
            break

    if rank is None:
        return jsonify({"success": False, "message": "You did not participate in yesterday's competition."})

    reward = 0
    if rank == 1:
        reward = prize_pool * 0.5
    elif rank == 2:
        reward = prize_pool * 0.25
    elif rank == 3:
        reward = prize_pool * 0.125
    elif 4 <= rank <=10:
        reward = prize_pool * 0.125 / 7

    reward = round(reward, 2)

    start_idx = max(0, rank - 3)
    end_idx = min(len(players), rank + 2)
    snippet = players[start_idx:end_idx]

    return jsonify({
        "success": True,
        "rank": rank,
        "reward": reward,
        "snippet": snippet
    })

@app.route('/api/claim_reward', methods=['POST'])
def claim_reward():
    daily_reset_if_needed()
    username = request.json.get('username')
    if claimed_rewards.get(username):
        return jsonify({"success": False, "message": "Reward already claimed or expired."})
    claimed_rewards[username] = True
    return jsonify({"success": True, "message": "Reward claimed successfully! (Simulated)"})

@app.route('/api/check_paid', methods=['POST'])
def check_paid():
    daily_reset_if_needed()
    username = request.json.get('username')
    users = load_json(USER_FILE)['users']
    user = next((u for u in users if u['username'] == username), None)
    if user:
        return jsonify({"paid": user.get('paid', False)})
    return jsonify({"paid": False})

@app.route('/')
def home():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)

