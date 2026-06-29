from app import create_app

app = create_app()

if __name__ == '__main__':
    # Chạy ứng dụng trên cổng 5000 ở localhost
    app.run(host='127.0.0.1', port=5000, debug=True)
