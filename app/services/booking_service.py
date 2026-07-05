from app.database import get_db_connection
from app.exceptions import HotelBookingException
import pymysql

# Dữ liệu phòng mẫu khi chạy ở chế độ PREVIEW (không có DB)
MOCK_PHONG = [
    {"MaPhong": 1, "TenPhong": "101", "Tang": 1, "TenLoai": "Standard", "SucChuaToiDa": 2, "GiaTieuChuan": 800000, "TrangThai": "Trong"},
    {"MaPhong": 2, "TenPhong": "102", "Tang": 1, "TenLoai": "Standard", "SucChuaToiDa": 2, "GiaTieuChuan": 850000, "TrangThai": "Trong"},
    {"MaPhong": 3, "TenPhong": "201", "Tang": 2, "TenLoai": "Deluxe", "SucChuaToiDa": 2, "GiaTieuChuan": 1400000, "TrangThai": "Trong"},
    {"MaPhong": 4, "TenPhong": "202", "Tang": 2, "TenLoai": "Deluxe", "SucChuaToiDa": 3, "GiaTieuChuan": 1600000, "TrangThai": "Dang_O"},
    {"MaPhong": 5, "TenPhong": "301", "Tang": 3, "TenLoai": "Suite", "SucChuaToiDa": 4, "GiaTieuChuan": 3000000, "TrangThai": "Dang_Don_Dep"},
    {"MaPhong": 6, "TenPhong": "302", "Tang": 3, "TenLoai": "Suite", "SucChuaToiDa": 4, "GiaTieuChuan": 3500000, "TrangThai": "Bao_Tri"},
]

def kiem_tra_phong_trong(ngay_checkin, ngay_checkout, loai=None, gia_min=None, gia_max=None):
    conn = get_db_connection()
    if conn is None:
        # Chế độ Preview
        rooms = [r for r in MOCK_PHONG if r["TrangThai"] == "Trong"]
        if loai:
            rooms = [r for r in rooms if r["TenLoai"] == loai]
        if gia_min:
            rooms = [r for r in rooms if r["GiaTieuChuan"] >= int(gia_min)]
        if gia_max:
            rooms = [r for r in rooms if r["GiaTieuChuan"] <= int(gia_max)]
        return rooms

    try:
        with conn.cursor() as cursor:
            # Gọi Stored Procedure sp_KiemTraPhongTrong
            cursor.callproc('sp_KiemTraPhongTrong', (ngay_checkin, ngay_checkout))
            rooms = cursor.fetchall()
            
            # Thực hiện lọc thêm ở Backend đối với các tiêu chí tìm kiếm phụ
            if loai:
                rooms = [r for r in rooms if r.get("TenLoai") == loai]
            if gia_min:
                rooms = [r for r in rooms if r.get("GiaTieuChuan", 0) >= int(gia_min)]
            if gia_max:
                rooms = [r for r in rooms if r.get("GiaTieuChuan", 0) <= int(gia_max)]
            return rooms
    except pymysql.MySQLError as e:
        errno = e.args[0] if e.args else 50000
        if isinstance(errno, int) and errno < 0:
            errno = 65536 + errno
        msg = e.args[1] if len(e.args) > 1 else str(e)
        raise HotelBookingException(errno, msg)
    finally:
        conn.close()

def tao_dat_phong(ma_kh, ma_phong, ngay_checkin, ngay_checkout, tien_coc):
    from datetime import datetime, date
    
    # Kiểm tra ngày đặt phòng hợp lệ (phải trước ít nhất 1 ngày)
    try:
        if isinstance(ngay_checkin, str):
            checkin_date = datetime.strptime(ngay_checkin, "%Y-%m-%d").date()
        else:
            checkin_date = ngay_checkin
            
        if checkin_date <= date.today():
            raise HotelBookingException(51004, "Chỉ được phép đặt phòng trước ít nhất 1 ngày.")
    except HotelBookingException:
        raise
    except Exception:
        pass

    conn = get_db_connection()
    if conn is None:
        # Chế độ Preview giả lập đặt phòng thành công
        return True

    try:
        import time
        conn.autocommit(False)
        with conn.cursor() as cursor:
            # 1. Quét lịch sử đặt phòng trùng lặp (❌ KHÔNG dùng FOR UPDATE hay SERIALIZABLE)
            cursor.execute("""
                SELECT COUNT(*) AS ConflictCount
                FROM DatPhong
                WHERE MaPhong = %s
                  AND NgayCheckIn < %s
                  AND NgayCheckOut > %s
                  AND TrangThaiDon IN ('Cho_Duyet', 'Da_Coc', 'Da_Nhan_Phong')
            """, (ma_phong, ngay_checkout, ngay_checkin))
            conflict = cursor.fetchone()
            
            # ═══ GIẢ LẬP TRỄ 2 GIÂY ═══
            # Giúp giao dịch đặt phòng hoàn tất nhanh hơn (chỉ chờ 2 giây)
            time.sleep(2)
            
            # 2. Thêm mới bản ghi đặt phòng
            cursor.execute("""
                INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon)
                VALUES (%s, %s, %s, %s, %s, 'Da_Coc')
            """, (ma_kh, ma_phong, ngay_checkin, ngay_checkout, tien_coc))
            
            conn.commit()
            return True
    except pymysql.MySQLError as e:
        conn.rollback()
        # Đẩy lỗi về Exception Handler
        errno = e.args[0] if e.args else 50000
        if isinstance(errno, int) and errno < 0:
            errno = 65536 + errno
        msg = e.args[1] if len(e.args) > 1 else str(e)
        raise HotelBookingException(errno, msg)
    finally:
        conn.close()

