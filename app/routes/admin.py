from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.services import admin_service
from app.error_codes import get_error_message
from app.database import get_db_connection

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/rooms')
def rooms():
    phong_list = admin_service.get_all_rooms()
    loai_phong_list = admin_service.get_all_room_types()
    return render_template('admin/rooms.html', phong_list=phong_list, loai_phong_list=loai_phong_list)

@admin_bp.route('/admin/add-room', methods=['POST'])
def add_room():
    ten_phong = request.form.get('ten_phong')
    tang = request.form.get('tang')
    ma_loai_phong = request.form.get('ma_loai_phong')
    
    try:
        admin_service.them_phong(ten_phong, tang, ma_loai_phong)
        flash(f"Thêm phòng {ten_phong} thành công!", "success")
    except Exception as e:
        errno = getattr(e, 'errno', None)
        error_msg = get_error_message(errno, getattr(e, 'message', str(e))) if errno else str(e)
        flash(f"Lỗi thêm phòng: {error_msg}", "error")
        
    return redirect(url_for('admin.rooms'))


@admin_bp.route('/admin/checkin', methods=['GET', 'POST'])
def checkin():
    if request.method == 'GET':
        pending = admin_service.get_pending_bookings()
        return render_template('admin/checkin.html', pending_bookings=pending)
    
    # POST
    ma_dat_phong = request.form.get('ma_dat_phong')
    try:
        admin_service.checkin(ma_dat_phong)
        flash(f"Check-in thành công cho đơn đặt phòng #{ma_dat_phong}!", "success")
    except Exception as e:
        errno = getattr(e, 'errno', None)
        error_msg = get_error_message(errno, getattr(e, 'message', str(e))) if errno else str(e)
        flash(f"Lỗi Check-in: {error_msg}", "error")
        
    return redirect(url_for('admin.checkin'))

@admin_bp.route('/admin/cancel-booking', methods=['POST'])
def cancel_booking():
    ma_dat_phong = request.form.get('ma_dat_phong')
    try:
        # Lấy thông tin tiền cọc trước khi hủy để đối chiếu hiển thị hoàn cọc
        conn = get_db_connection()
        tien_coc_truoc = 0
        days_diff = 3 # mặc định hủy sớm nếu không kết nối được DB
        
        if conn is not None:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT TienCoc, NgayCheckIn, DATEDIFF(NgayCheckIn, CURDATE()) AS DaysDiff FROM DatPhong WHERE MaDatPhong = %s", (ma_dat_phong,))
                    res = cursor.fetchone()
                    if res:
                        tien_coc_truoc = res['TienCoc'] or 0
                        days_diff = res['DaysDiff'] if res['DaysDiff'] is not None else 3
            except Exception:
                pass
            finally:
                conn.close()

        # Thực thi thủ tục hủy
        admin_service.huy_dat_phong(ma_dat_phong)
        
        # Tạo thông báo thông minh dựa trên khoảng cách ngày hủy
        if days_diff < 3:
            flash(f"Hủy đơn #{ma_dat_phong} thành công! (Hủy muộn dưới 3 ngày: Phạt 100% cọc. Khách hàng mất {tien_coc_truoc:,.0f} VNĐ cọc, hoàn trả 0 VNĐ)", "warning")
        else:
            flash(f"Hủy đơn #{ma_dat_phong} thành công! (Hủy sớm >= 3 ngày: Hoàn cọc 100%. Đã xử lý hoàn trả {tien_coc_truoc:,.0f} VNĐ cho khách)", "success")
            
    except Exception as e:
        errno = getattr(e, 'errno', None)
        error_msg = get_error_message(errno, getattr(e, 'message', str(e))) if errno else str(e)
        flash(f"Lỗi hủy đơn: {error_msg}", "error")
        
    return redirect(url_for('admin.checkin'))

@admin_bp.route('/admin/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'GET':
        active = admin_service.get_active_bookings()
        return render_template('admin/checkout.html', active_bookings=active)
    
    # POST
    ma_dat_phong = request.form.get('ma_dat_phong')
    tien_dich_vu = request.form.get('tien_dich_vu', 0)
    
    try:
        # Trước khi checkout, tính tiền phòng để hiển thị hóa đơn đẹp cho lễ tân
        conn = get_db_connection()
        tien_phong = 0
        total_payment = 0
        customer_name = ""
        room_num = ""
        
        if conn is not None:
            try:
                with conn.cursor() as cursor:
                    # Truy vấn thông tin chi tiết để gọi hàm scalar fn_TinhTienPhong
                    query = """
                        SELECT dp.NgayCheckIn, dp.NgayCheckOut, lp.GiaTieuChuan, kh.HoTen, p.TenPhong
                        FROM DatPhong dp
                        JOIN KhachHang kh ON dp.MaKH = kh.MaKH
                        JOIN Phong p ON dp.MaPhong = p.MaPhong
                        JOIN LoaiPhong lp ON p.MaLoaiPhong = lp.MaLoaiPhong
                        WHERE dp.MaDatPhong = %s
                    """
                    cursor.execute(query, (ma_dat_phong,))
                    info = cursor.fetchone()
                    if info:
                        customer_name = info['HoTen']
                        room_num = info['TenPhong']
                        # Gọi hàm scalar fn_TinhTienPhong trong SQL
                        cursor.execute(
                            "SELECT fn_TinhTienPhong(%s, %s, %s) AS TienPhong",
                            (info['GiaTieuChuan'], info['NgayCheckIn'], info['NgayCheckOut'])
                        )
                        res = cursor.fetchone()
                        if res:
                            tien_phong = res['TienPhong']
            except Exception as db_err:
                pass
            finally:
                conn.close()

        # Thực thi thủ tục checkout
        admin_service.checkout(ma_dat_phong, tien_dich_vu)
        
        # Tạo thông báo hóa đơn thành công
        total_payment = float(tien_phong) + float(tien_dich_vu)
        flash(f"Check-out thành công đơn #{ma_dat_phong}! Khách hàng: {customer_name or 'Mock Guest'}, Phòng: {room_num or 'Mock Room'}. Tổng thanh toán: {total_payment:,.0f} VNĐ (Tiền phòng: {tien_phong:,.0f} VNĐ + Dịch vụ: {float(tien_dich_vu):,.0f} VNĐ)", "success")
        
    except Exception as e:
        errno = getattr(e, 'errno', None)
        error_msg = get_error_message(errno, getattr(e, 'message', str(e))) if errno else str(e)
        flash(f"Lỗi Check-out: {error_msg}", "error")
        
    return redirect(url_for('admin.checkout'))

@admin_bp.route('/admin/toggle-room', methods=['POST'])
def toggle_room():
    ma_phong = request.form.get('ma_phong')
    trang_thai_moi = request.form.get('trang_thai_moi')
    
    try:
        admin_service.khoa_mo_phong(ma_phong, trang_thai_moi)
        status_text = "Mở khóa thành công" if trang_thai_moi == 'Trong' else "Khóa bảo trì thành công"
        flash(f"Phòng #{ma_phong}: {status_text}!", "success")
    except Exception as e:
        errno = getattr(e, 'errno', None)
        error_msg = get_error_message(errno, getattr(e, 'message', str(e))) if errno else str(e)
        flash(f"Lỗi cập nhật trạng thái phòng: {error_msg}", "error")
        
    return redirect(url_for('admin.rooms'))

@admin_bp.route('/debug-checkout')
def debug_checkout():
    conn = get_db_connection()
    db_mode = "DATABASE" if conn is not None else "PREVIEW"
    if conn:
        conn.close()
    try:
        admin_service.checkout(3, 0)
        return f"SUCCESS (Mode: {db_mode})"
    except Exception as e:
        import traceback
        return f"ERROR (Mode: {db_mode}): {str(e)}<pre>{traceback.format_exc()}</pre>"


