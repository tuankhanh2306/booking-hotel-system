-- ====================================================================
-- CHƯƠNG II: THỦ TỤC LƯU TRỮ VÀ HÀM NGHIỆP VỤ LÕI (STORED PROCEDURES & FUNCTIONS)
-- ====================================================================

DELIMITER //

-- ====================================================================
-- 1. HÀM TÍNH TIỀN PHÒNG (SCALAR FUNCTION)
-- Công thức: Số ngày lưu trú * Giá tiêu chuẩn hạng phòng
-- ====================================================================
DROP FUNCTION IF EXISTS fn_TinhTienPhong//

CREATE FUNCTION fn_TinhTienPhong(
    p_GiaTieuChuan DECIMAL(12, 2),
    p_NgayCheckIn DATE,
    p_NgayCheckOut DATE
) 
RETURNS DECIMAL(12, 2)
DETERMINISTIC
BEGIN
    DECLARE v_SoNgay INT;
    SET v_SoNgay = DATEDIFF(p_NgayCheckOut, p_NgayCheckIn);
    -- Nếu khách checkout trong ngày nhận phòng, tính là 1 đêm
    IF v_SoNgay <= 0 THEN
        SET v_SoNgay = 1;
    END IF;
    RETURN v_SoNgay * p_GiaTieuChuan;
END//

-- ====================================================================
-- 2. THỦ TỤC TÌM PHÒNG TRỐNG (STORED PROCEDURE)
-- Điều kiện: Trạng thái vật lý = 'Trong' và không trùng lịch đặt phòng hoạt động
-- ====================================================================
DROP PROCEDURE IF EXISTS sp_KiemTraPhongTrong//

CREATE PROCEDURE sp_KiemTraPhongTrong(
    IN p_NgayCheckIn DATE,
    IN p_NgayCheckOut DATE
)
BEGIN
    -- Ràng buộc ngày đặt
    IF p_NgayCheckOut <= p_NgayCheckIn THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Ngay Check-out phai lon hon Ngay Check-in.', MYSQL_ERRNO = 51001;
    END IF;

    SELECT 
        p.MaPhong,
        p.TenPhong,
        p.Tang,
        p.TrangThai,
        lp.TenLoai,
        lp.GiaTieuChuan,
        lp.SucChuaToiDa
    FROM Phong p
    JOIN LoaiPhong lp ON p.MaLoaiPhong = lp.MaLoaiPhong
    WHERE p.TrangThai = 'Trong'
      AND NOT EXISTS (
          SELECT 1 
          FROM DatPhong dp
          WHERE dp.MaPhong = p.MaPhong
            -- Xung đột giao cắt thời gian (Overlap)
            AND dp.NgayCheckIn < p_NgayCheckOut
            AND dp.NgayCheckOut > p_NgayCheckIn
            -- Đơn đặt đang hoạt động
            AND dp.TrangThaiDon IN ('Cho_Duyet', 'Da_Coc', 'Da_Nhan_Phong')
      )
    ORDER BY lp.GiaTieuChuan ASC, p.TenPhong ASC;
END//

-- ====================================================================
-- 3. GIAO TÁC CỐT LÕI ĐẶT PHÒNG CHỐNG OVERBOOKING (STORED PROCEDURE)
-- Ép mức cô lập bảo mật cao nhất: SERIALIZABLE
-- Khóa dòng độc quyền trên dải chỉ mục bằng từ khóa: FOR UPDATE
-- ====================================================================
DROP PROCEDURE IF EXISTS sp_TaoDatPhong//

CREATE PROCEDURE sp_TaoDatPhong(
    IN p_MaKH INT,
    IN p_MaPhong INT,
    IN p_NgayCheckIn DATE,
    IN p_NgayCheckOut DATE,
    IN p_TienCoc DECIMAL(12, 2)
)
BEGIN
    DECLARE v_RoomStatus VARCHAR(20);
    DECLARE v_ConflictCount INT;
    DECLARE v_KHExists INT;

    -- (Vô hiệu hóa TRANSACTION ISOLATION và FOR UPDATE để demo lỗi concurrency)
    -- SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
    
    START TRANSACTION;

    -- 1. Kiểm tra ngày Check-in/Check-out hợp lệ
    IF p_NgayCheckOut <= p_NgayCheckIn THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Ngay Check-out khong hop le.', MYSQL_ERRNO = 51001;
    END IF;

    -- 2. Kiểm tra số tiền cọc hợp lệ
    IF p_TienCoc < 0 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Tien coc khong hop le.', MYSQL_ERRNO = 51002;
    END IF;

    -- 3. Kiểm tra sự tồn tại của Khách hàng
    SELECT COUNT(*) INTO v_KHExists FROM KhachHang WHERE MaKH = p_MaKH;
    IF v_KHExists = 0 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Khach hang khong ton tai.', MYSQL_ERRNO = 51003;
    END IF;

    -- 4. Kiểm tra sự tồn tại của Phòng (Không khóa FOR UPDATE)
    SET v_RoomStatus = NULL;
    SELECT TrangThai INTO v_RoomStatus 
    FROM Phong WHERE MaPhong = p_MaPhong;
    
    IF v_RoomStatus IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Phong khong ton tai.', MYSQL_ERRNO = 51003;
    END IF;

    -- 5. Đánh chặn nếu phòng đang trong tình trạng bảo trì
    IF v_RoomStatus = 'Bao_Tri' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Phong dang trong trang thai bao tri.', MYSQL_ERRNO = 52003;
    END IF;

    -- 6. Quét dải lịch sử đặt phòng chồng lấn (Không khóa FOR UPDATE)
    SELECT COUNT(*) INTO v_ConflictCount
    FROM DatPhong
    WHERE MaPhong = p_MaPhong
      AND NgayCheckIn < p_NgayCheckOut
      AND NgayCheckOut > p_NgayCheckIn
      AND TrangThaiDon IN ('Cho_Duyet', 'Da_Coc', 'Da_Nhan_Phong');

    -- 7. Ném lỗi Overbooking (Vô hiệu hóa để demo lỗi đặt trùng phòng)
    -- IF v_ConflictCount > 0 THEN
    --     SIGNAL SQLSTATE '45000'
    --     SET MESSAGE_TEXT = 'Phong khong con trong (Overbooking).', MYSQL_ERRNO = 52001;
    -- END IF;

    -- 8. Thêm mới bản ghi đặt phòng
    INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon)
    VALUES (p_MaKH, p_MaPhong, p_NgayCheckIn, p_NgayCheckOut, p_TienCoc, 'Da_Coc');

    COMMIT;
END//

-- ====================================================================
-- 4. GIAO TÁC HỦY ĐẶT PHÒNG PHẠT TIỀN CỌC (STORED PROCEDURE)
-- Tự động phạt cọc về 0 nếu hủy muộn dưới 3 ngày so với ngày nhận phòng
-- ====================================================================
DROP PROCEDURE IF EXISTS sp_HuyDatPhong//

CREATE PROCEDURE sp_HuyDatPhong(
    IN p_MaDatPhong INT
)
BEGIN
    DECLARE v_NgayCheckIn DATE;
    DECLARE v_TrangThaiDon VARCHAR(20);
    DECLARE v_DaysDiff INT;

    START TRANSACTION;

    -- 1. Kiểm tra đơn đặt phòng tồn tại và khóa độc quyền (Tương thích only_full_group_by)
    SET v_NgayCheckIn = NULL;
    SET v_TrangThaiDon = NULL;
    
    SELECT NgayCheckIn, TrangThaiDon INTO v_NgayCheckIn, v_TrangThaiDon
    FROM DatPhong WHERE MaDatPhong = p_MaDatPhong FOR UPDATE;

    IF v_NgayCheckIn IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Don dat phong khong ton tai.', MYSQL_ERRNO = 51003;
    END IF;

    -- 2. Kiểm tra xem đơn đặt phòng có cho phép hủy hay không
    IF v_TrangThaiDon NOT IN ('Cho_Duyet', 'Da_Coc') THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Trang thai don khong cho phep huy.', MYSQL_ERRNO = 52002;
    END IF;

    -- 3. Tính khoảng cách số ngày để áp dụng chính sách hoàn cọc
    SET v_DaysDiff = DATEDIFF(v_NgayCheckIn, CURDATE());

    -- Nếu hủy muộn (dưới 3 ngày) phạt cọc về 0, ngược lại hoàn 100% cọc
    IF v_DaysDiff < 3 THEN
        UPDATE DatPhong 
        SET TrangThaiDon = 'Da_Huy', TienCoc = 0.00 
        WHERE MaDatPhong = p_MaDatPhong;
    ELSE
        UPDATE DatPhong 
        SET TrangThaiDon = 'Da_Huy' 
        WHERE MaDatPhong = p_MaDatPhong;
    END IF;

    COMMIT;
END//

-- ====================================================================
-- 5. GIAO TÁC XỬ LÝ NHẬN PHÒNG CHECK-IN (STORED PROCEDURE)
-- Idempotency: Kiểm tra trạng thái đơn đặt và phòng trước khi cập nhật
-- ====================================================================
DROP PROCEDURE IF EXISTS sp_XuLyCheckIn//

CREATE PROCEDURE sp_XuLyCheckIn(
    IN p_MaDatPhong INT
)
BEGIN
    DECLARE v_MaPhong INT;
    DECLARE v_TrangThaiDon VARCHAR(20);
    DECLARE v_TrangThaiPhong VARCHAR(20);

    START TRANSACTION;

    -- 1. Lấy thông tin đơn (Không khóa FOR UPDATE)
    SET v_MaPhong = NULL;
    SET v_TrangThaiDon = NULL;
    
    SELECT MaPhong, TrangThaiDon INTO v_MaPhong, v_TrangThaiDon
    FROM DatPhong WHERE MaDatPhong = p_MaDatPhong;

    IF v_MaPhong IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Don dat phong khong ton tai.', MYSQL_ERRNO = 51003;
    END IF;

    -- 2. Kiểm tra trạng thái đơn hàng hợp lệ
    IF v_TrangThaiDon NOT IN ('Cho_Duyet', 'Da_Coc') THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Trang thai don khong cho phep check-in.', MYSQL_ERRNO = 52002;
    END IF;

    -- 3. Kiểm tra trạng thái vật lý của phòng (Vô hiệu hóa để demo lỗi check-in đè lên phòng đang có khách hoặc bảo trì)
    -- SELECT TrangThai INTO v_TrangThaiPhong FROM Phong WHERE MaPhong = v_MaPhong;
    -- IF v_TrangThaiPhong <> 'Trong' THEN
    --     SIGNAL SQLSTATE '45000'
    --     SET MESSAGE_TEXT = 'Phong dang khong san sang (ban hoac bao tri).', MYSQL_ERRNO = 52003;
    -- END IF;

    -- 4. Cập nhật đồng thời đơn đặt và trạng thái phòng
    UPDATE DatPhong SET TrangThaiDon = 'Da_Nhan_Phong' WHERE MaDatPhong = p_MaDatPhong;
    UPDATE Phong SET TrangThai = 'Dang_O' WHERE MaPhong = v_MaPhong;

    COMMIT;
END//

-- ====================================================================
-- 6. GIAO TÁC XỬ LÝ TRẢ PHÒNG CHECK-OUT (STORED PROCEDURE)
-- Tự động gọi hàm tính tiền phòng, lập hóa đơn và chuyển trạng thái phòng
-- ====================================================================
DROP PROCEDURE IF EXISTS sp_XuLyCheckOut//

CREATE PROCEDURE sp_XuLyCheckOut(
    IN p_MaDatPhong INT,
    IN p_TienDichVu DECIMAL(12, 2)
)
BEGIN
    DECLARE v_MaPhong INT;
    DECLARE v_TrangThaiDon VARCHAR(20);
    DECLARE v_NgayCheckIn DATE;
    DECLARE v_NgayCheckOut DATE;
    DECLARE v_GiaTieuChuan DECIMAL(12, 2);
    DECLARE v_TienPhong DECIMAL(12, 2);

    START TRANSACTION;

    -- 1. Kiểm tra tham số tiền dịch vụ
    IF p_TienDichVu < 0 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Tien dich vu khong hop le.', MYSQL_ERRNO = 51002;
    END IF;

    -- 2. Lấy thông tin chi tiết hóa đơn và khóa dòng độc quyền (Tương thích only_full_group_by)
    SET v_MaPhong = NULL;
    
    SELECT dp.MaPhong, dp.TrangThaiDon, dp.NgayCheckIn, dp.NgayCheckOut, lp.GiaTieuChuan
    INTO v_MaPhong, v_TrangThaiDon, v_NgayCheckIn, v_NgayCheckOut, v_GiaTieuChuan
    FROM DatPhong dp
    JOIN Phong p ON dp.MaPhong = p.MaPhong
    JOIN LoaiPhong lp ON p.MaLoaiPhong = lp.MaLoaiPhong
    WHERE dp.MaDatPhong = p_MaDatPhong FOR UPDATE;

    IF v_MaPhong IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Don dat phong khong ton tai.', MYSQL_ERRNO = 51003;
    END IF;

    -- 3. Kiểm tra xem đơn có đang ở trạng thái nhận phòng không
    IF v_TrangThaiDon <> 'Da_Nhan_Phong' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Don chua thuc hien Check-in.', MYSQL_ERRNO = 52002;
    END IF;

    -- 4. Gọi Hàm Scalar fn_TinhTienPhong để tính toán tiền phòng thực tế
    SET v_TienPhong = fn_TinhTienPhong(v_GiaTieuChuan, v_NgayCheckIn, v_NgayCheckOut);

    -- 5. Tạo hóa đơn tài chính mới
    INSERT INTO HoaDon (MaDatPhong, TienPhong, TienDichVu, TongTien)
    VALUES (p_MaDatPhong, v_TienPhong, p_TienDichVu, (v_TienPhong + p_TienDichVu));

    -- 6. Cập nhật đơn đặt phòng sang Hoàn thành (Sự kiện này kích hoạt trg_CapNhatTrangThaiPhong tự đổi trạng thái phòng sang 'Dang_Don_Dep')
    UPDATE DatPhong SET TrangThaiDon = 'Hoan_Thanh' WHERE MaDatPhong = p_MaDatPhong;

    COMMIT;
END//

-- ====================================================================
-- 7. THỦ TỤC KHÓA/MỞ PHÒNG BẢO TRÌ DÀNH CHO ADMIN (STORED PROCEDURE)
-- ====================================================================
DROP PROCEDURE IF EXISTS sp_Admin_KhoaMoPhong//

CREATE PROCEDURE sp_Admin_KhoaMoPhong(
    IN p_MaPhong INT,
    IN p_TrangThaiMoi VARCHAR(20)
)
BEGIN
    DECLARE v_TrangThaiHienTai VARCHAR(20);

    START TRANSACTION;

    -- 1. Kiểm tra tham số trạng thái mới
    IF p_TrangThaiMoi NOT IN ('Trong', 'Bao_Tri') THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Trang thai moi khong hop le.', MYSQL_ERRNO = 52002;
    END IF;

    -- 2. Kiểm tra sự tồn tại của phòng (Không khóa FOR UPDATE)
    SET v_TrangThaiHienTai = NULL;
    SELECT TrangThai INTO v_TrangThaiHienTai 
    FROM Phong WHERE MaPhong = p_MaPhong;

    IF v_TrangThaiHienTai IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Phong khong ton tai.', MYSQL_ERRNO = 51003;
    END IF;

    -- 3. Ngăn cản khóa bảo trì khi phòng đang có khách ở (Vô hiệu hóa để demo lỗi khóa phòng khi khách đang ở)
    -- IF v_TrangThaiHienTai = 'Dang_O' THEN
    --     SIGNAL SQLSTATE '45000'
    --     SET MESSAGE_TEXT = 'Phong dang co khach luu tru, khong the khoa.', MYSQL_ERRNO = 52002;
    -- END IF;

    -- 4. Thực hiện cập nhật
    UPDATE Phong SET TrangThai = p_TrangThaiMoi WHERE MaPhong = p_MaPhong;

    COMMIT;
END//

DELIMITER ;
