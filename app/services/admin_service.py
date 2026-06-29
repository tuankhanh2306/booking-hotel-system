from app.database import get_db_connection
from app.exceptions import HotelBookingException
from app.services.booking_service import MOCK_PHONG
import pymysql

# MOCK Data cho Bookings trong chế độ PREVIEW
MOCK_BOOKINGS = [
    {"MaDatPhong": 1, "HoTen": "Nguyễn Văn A", "TenPhong": "101", "NgayCheckIn": "2026-06-25", "NgayCheckOut": "2026-06-28", "TienCoc": 200000, "TrangThaiDon": "Da_Coc"},
    {"MaDatPhong": 2, "HoTen": "Trần Thị B", "TenPhong": "102", "NgayCheckIn": "2026-06-26", "NgayCheckOut": "2026-06-30", "TienCoc": 300000, "TrangThaiDon": "Cho_Duyet"},
]

MOCK_ACTIVE_BOOKINGS = [
    {"MaDatPhong": 3, "HoTen": "Phạm Văn C", "TenPhong": "202", "NgayCheckIn": "2026-06-20", "NgayCheckOut": "2026-06-25", "GiaTieuChuan": 1600000, "TrangThaiDon": "Da_Nhan_Phong"},
]

def get_all_rooms():
    conn = get_db_connection()
    if conn is None:
        return MOCK_PHONG
    
    try:
        with conn.cursor() as cursor:
            # Query lấy toàn bộ phòng kèm thông tin lưu trú hiện tại (nếu có)
            query = """
                SELECT 
                    p.MaPhong, 
                    p.TenPhong, 
                    p.Tang, 
                    p.TrangThai, 
                    lp.TenLoai, 
                    lp.GiaTieuChuan, 
                    lp.SucChuaToiDa,
                    kh.HoTen AS TenKhachHang,
                    dp.NgayCheckIn,
                    dp.NgayCheckOut,
                    dp.MaDatPhong
                FROM Phong p
                JOIN LoaiPhong lp ON p.MaLoaiPhong = lp.MaLoaiPhong
                LEFT JOIN DatPhong dp ON p.MaPhong = dp.MaPhong AND dp.TrangThaiDon = 'Da_Nhan_Phong'
                LEFT JOIN KhachHang kh ON dp.MaKH = kh.MaKH
                ORDER BY p.TenPhong
            """
            cursor.execute(query)
            return cursor.fetchall()
    except Exception as e:
        return MOCK_PHONG
    finally:
        if conn:
            conn.close()

def get_pending_bookings():
    conn = get_db_connection()
    if conn is None:
        return MOCK_BOOKINGS
    
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT dp.MaDatPhong, kh.HoTen, p.TenPhong, dp.NgayCheckIn, dp.NgayCheckOut, dp.TienCoc, dp.TrangThaiDon
                FROM DatPhong dp
                JOIN KhachHang kh ON dp.MaKH = kh.MaKH
                JOIN Phong p ON dp.MaPhong = p.MaPhong
                WHERE dp.TrangThaiDon IN ('Cho_Duyet', 'Da_Coc')
                ORDER BY dp.MaDatPhong DESC
            """
            cursor.execute(query)
            return cursor.fetchall()
    except Exception as e:
        return MOCK_BOOKINGS
    finally:
        if conn:
            conn.close()

def get_active_bookings():
    conn = get_db_connection()
    if conn is None:
        return MOCK_ACTIVE_BOOKINGS
    
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT dp.MaDatPhong, kh.HoTen, p.TenPhong, dp.NgayCheckIn, dp.NgayCheckOut, lp.GiaTieuChuan, dp.TrangThaiDon
                FROM DatPhong dp
                JOIN KhachHang kh ON dp.MaKH = kh.MaKH
                JOIN Phong p ON dp.MaPhong = p.MaPhong
                JOIN LoaiPhong lp ON p.MaLoaiPhong = lp.MaLoaiPhong
                WHERE dp.TrangThaiDon = 'Da_Nhan_Phong'
                ORDER BY dp.MaDatPhong DESC
            """
            cursor.execute(query)
            return cursor.fetchall()
    except Exception as e:
        return MOCK_ACTIVE_BOOKINGS
    finally:
        if conn:
            conn.close()

def checkin(ma_dat_phong):
    conn = get_db_connection()
    if conn is None:
        # Chế độ Preview
        target_booking = None
        for b in MOCK_BOOKINGS:
            if b["MaDatPhong"] == int(ma_dat_phong):
                target_booking = b
                break
        if target_booking:
            target_booking["TrangThaiDon"] = "Da_Nhan_Phong"
            # Thêm vào MOCK_ACTIVE_BOOKINGS
            MOCK_ACTIVE_BOOKINGS.append({
                "MaDatPhong": target_booking["MaDatPhong"],
                "HoTen": target_booking["HoTen"],
                "TenPhong": target_booking["TenPhong"],
                "NgayCheckIn": target_booking["NgayCheckIn"],
                "NgayCheckOut": target_booking["NgayCheckOut"],
                "GiaTieuChuan": 800000.0,
                "TrangThaiDon": "Da_Nhan_Phong"
            })
            # Xóa khỏi MOCK_BOOKINGS
            MOCK_BOOKINGS.remove(target_booking)
            # Cập nhật trạng thái phòng tương ứng thành 'Dang_O'
            for p in MOCK_PHONG:
                if p["TenPhong"] == target_booking["TenPhong"]:
                    p["TrangThai"] = "Dang_O"
                    p["TenKhachHang"] = target_booking["HoTen"]
                    p["NgayCheckIn"] = target_booking["NgayCheckIn"]
                    p["NgayCheckOut"] = target_booking["NgayCheckOut"]
                    break
        return True

    try:
        with conn.cursor() as cursor:
            # Gọi Stored Procedure sp_XuLyCheckIn
            cursor.callproc('sp_XuLyCheckIn', (ma_dat_phong,))
            conn.commit()
            return True
    except pymysql.MySQLError as e:
        conn.rollback()
        errno = e.args[0] if e.args else 50000
        if isinstance(errno, int) and errno < 0:
            errno = 65536 + errno
        msg = e.args[1] if len(e.args) > 1 else str(e)
        raise HotelBookingException(errno, msg)
    finally:
        conn.close()

def huy_dat_phong(ma_dat_phong):
    conn = get_db_connection()
    if conn is None:
        # Chế độ Preview
        target_booking = None
        for b in MOCK_BOOKINGS:
            if b["MaDatPhong"] == int(ma_dat_phong):
                target_booking = b
                break
        if target_booking:
            MOCK_BOOKINGS.remove(target_booking)
        return True

    try:
        with conn.cursor() as cursor:
            # Gọi Stored Procedure sp_HuyDatPhong
            cursor.callproc('sp_HuyDatPhong', (ma_dat_phong,))
            conn.commit()
            return True
    except pymysql.MySQLError as e:
        conn.rollback()
        errno = e.args[0] if e.args else 50000
        if isinstance(errno, int) and errno < 0:
            errno = 65536 + errno
        msg = e.args[1] if len(e.args) > 1 else str(e)
        raise HotelBookingException(errno, msg)
    finally:
        conn.close()

def checkout(ma_dat_phong, tien_dich_vu):
    conn = get_db_connection()
    if conn is None:
        # Chế độ Preview
        target_booking = None
        for b in MOCK_ACTIVE_BOOKINGS:
            if b["MaDatPhong"] == int(ma_dat_phong):
                target_booking = b
                break
        if target_booking:
            # Xóa khỏi MOCK_ACTIVE_BOOKINGS
            MOCK_ACTIVE_BOOKINGS.remove(target_booking)
            # Cập nhật trạng thái phòng tương ứng thành 'Dang_Don_Dep'
            for p in MOCK_PHONG:
                if p["TenPhong"] == target_booking["TenPhong"]:
                    p["TrangThai"] = "Dang_Don_Dep"
                    p.pop("TenKhachHang", None)
                    p.pop("NgayCheckIn", None)
                    p.pop("NgayCheckOut", None)
                    break
        return True

    try:
        with conn.cursor() as cursor:
            # Gọi Stored Procedure sp_XuLyCheckOut
            cursor.callproc('sp_XuLyCheckOut', (ma_dat_phong, tien_dich_vu))
            conn.commit()
            return True
    except pymysql.MySQLError as e:
        conn.rollback()
        errno = e.args[0] if e.args else 50000
        if isinstance(errno, int) and errno < 0:
            errno = 65536 + errno
        msg = e.args[1] if len(e.args) > 1 else str(e)
        raise HotelBookingException(errno, msg)
    finally:
        conn.close()

def khoa_mo_phong(ma_phong, trang_thai_moi):
    conn = get_db_connection()
    if conn is None:
        # Chế độ Preview
        for p in MOCK_PHONG:
            if p["MaPhong"] == int(ma_phong):
                p["TrangThai"] = trang_thai_moi
        return True

    try:
        with conn.cursor() as cursor:
            # Gọi Stored Procedure sp_Admin_KhoaMoPhong
            cursor.callproc('sp_Admin_KhoaMoPhong', (ma_phong, trang_thai_moi))
            conn.commit()
            return True
    except pymysql.MySQLError as e:
        conn.rollback()
        errno = e.args[0] if e.args else 50000
        if isinstance(errno, int) and errno < 0:
            errno = 65536 + errno
        msg = e.args[1] if len(e.args) > 1 else str(e)
        raise HotelBookingException(errno, msg)
    finally:
        conn.close()

def get_all_room_types():
    conn = get_db_connection()
    if conn is None:
        return [
            {"MaLoaiPhong": 1, "TenLoai": "Standard"},
            {"MaLoaiPhong": 2, "TenLoai": "Deluxe"},
            {"MaLoaiPhong": 3, "TenLoai": "Suite"}
        ]
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT MaLoaiPhong, TenLoai FROM LoaiPhong ORDER BY TenLoai")
            return cursor.fetchall()
    except Exception as e:
        return []
    finally:
        if conn:
            conn.close()

def them_phong(ten_phong, tang, ma_loai_phong):
    conn = get_db_connection()
    if conn is None:
        # Mock mode
        MOCK_PHONG.append({
            "MaPhong": len(MOCK_PHONG) + 1,
            "TenPhong": ten_phong,
            "Tang": int(tang),
            "TenLoai": "Standard", 
            "SucChuaToiDa": 2,
            "GiaTieuChuan": 800000.0,
            "TrangThai": "Trong"
        })
        return True

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO Phong (TenPhong, Tang, MaLoaiPhong, TrangThai) VALUES (%s, %s, %s, 'Trong')",
                (ten_phong, tang, ma_loai_phong)
            )
            conn.commit()
            return True
    except pymysql.MySQLError as e:
        conn.rollback()
        errno = e.args[0] if e.args else 50000
        if isinstance(errno, int) and errno < 0:
            errno = 65536 + errno
        msg = e.args[1] if len(e.args) > 1 else str(e)
        raise HotelBookingException(errno, msg)
    finally:
        conn.close()

