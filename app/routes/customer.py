from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.services import booking_service
from app.database import get_db_connection
from app.error_codes import get_error_message
from datetime import date

customer_bp = Blueprint('customer', __name__)

@customer_bp.route('/')
def index():
    return redirect(url_for('customer.search'))

@customer_bp.route('/customer/search')
def search():
    ngay_nhan = request.args.get('ngay_nhan')
    ngay_tra = request.args.get('ngay_tra')
    loai = request.args.get('loai')
    gia_min = request.args.get('gia_min')
    gia_max = request.args.get('gia_max')
    so_nguoi = request.args.get('so_nguoi')

    search_params = {
        "ngay_nhan": ngay_nhan,
        "ngay_tra": ngay_tra,
        "loai": loai,
        "gia_min": gia_min,
        "gia_max": gia_max,
        "so_nguoi": so_nguoi
    }

    today = date.today().isoformat()
    
    # Nếu không nhập ngày, hiển thị danh sách phòng mẫu nổi bật
    if not ngay_nhan or not ngay_tra:
        rooms = booking_service.get_all_rooms() if hasattr(booking_service, 'get_all_rooms') else booking_service.MOCK_PHONG
        # Lấy 6 phòng trống tiêu biểu
        rooms = [r for r in rooms if r.get("TrangThai", "Trong") == "Trong"][:6]
    else:
        try:
            rooms = booking_service.kiem_tra_phong_trong(ngay_nhan, ngay_tra, loai, gia_min, gia_max)
        except Exception as e:
            flash(getattr(e, 'message', str(e)), 'error')
            rooms = []

    # Mock statistics
    stats = {
        "tong_phong": len([r for r in (booking_service.get_all_rooms() if hasattr(booking_service, 'get_all_rooms') else booking_service.MOCK_PHONG) if r.get("TrangThai") == "Trong"]),
        "loai_phong": 3,
        "dat_phong_hom_nay": 12
    }

    return render_template(
        'customer/search.html',
        search=search_params,
        phong_list=rooms,
        stats=stats,
        today=today
    )

@customer_bp.route('/customer/booking', methods=['GET', 'POST'])
def booking():
    if request.method == 'GET':
        ma_phong = request.args.get('ma_phong')
        if not ma_phong:
            flash("Vui lòng chọn phòng để đặt.", "info")
            return redirect(url_for('customer.search'))
        
        # Lấy chi tiết phòng
        rooms = booking_service.get_all_rooms() if hasattr(booking_service, 'get_all_rooms') else booking_service.MOCK_PHONG
        selected_room = next((r for r in rooms if str(r.get("MaPhong")) == str(ma_phong)), None)
        
        return render_template('customer/booking.html', room=selected_room)

    # POST
    ma_phong = request.form.get('ma_phong')
    ho_ten = request.form.get('ho_ten')
    cccd = request.form.get('cccd')
    dien_thoai = request.form.get('dien_thoai')
    ngay_nhan = request.form.get('ngay_nhan')
    ngay_tra = request.form.get('ngay_tra')
    tien_coc = request.form.get('tien_coc', 0)

    try:
        # 1. Quản lý khách hàng: tìm hoặc tạo KhachHang mới
        conn = get_db_connection()
        ma_kh = 1 # mặc định cho preview mode
        
        if conn is not None:
            try:
                with conn.cursor() as cursor:
                    # Tìm theo CCCD
                    cursor.execute("SELECT MaKH FROM KhachHang WHERE CCCD = %s", (cccd,))
                    kh = cursor.fetchone()
                    if kh:
                        ma_kh = kh['MaKH']
                    else:
                        # Thêm khách hàng mới
                        cursor.execute(
                            "INSERT INTO KhachHang (HoTen, CCCD, DienThoai) VALUES (%s, %s, %s)",
                            (ho_ten, cccd, dien_thoai)
                        )
                        conn.commit()
                        ma_kh = cursor.lastrowid
            finally:
                conn.close()

        # 2. Gọi service tạo đơn đặt phòng (gọi sp_TaoDatPhong)
        booking_service.tao_dat_phong(ma_kh, ma_phong, ngay_nhan, ngay_tra, tien_coc)
        flash("Đặt phòng thành công! Nhân viên sẽ liên hệ sớm nhất.", "success")
        return redirect(url_for('customer.search'))
        
    except Exception as e:
        errno = getattr(e, 'errno', None)
        error_msg = get_error_message(errno, getattr(e, 'message', str(e))) if errno else str(e)
        flash(f"Lỗi đặt phòng: {error_msg}", "error")
        return redirect(url_for('customer.booking', ma_phong=ma_phong, ngay_nhan=ngay_nhan, ngay_tra=ngay_tra))

@customer_bp.route('/about')
def about():
    return render_template('about.html')
