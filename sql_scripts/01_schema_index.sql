-- Tái lập cấu trúc database sạch (Reset Schema)
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS HoaDon;
DROP TABLE IF EXISTS DatPhong;
DROP TABLE IF EXISTS KhachHang;
DROP TABLE IF EXISTS Phong;
DROP TABLE IF EXISTS LoaiPhong;
SET FOREIGN_KEY_CHECKS = 1;

-- 1. Bảng Loại Phòng
CREATE TABLE IF NOT EXISTS LoaiPhong (
    MaLoaiPhong INT AUTO_INCREMENT PRIMARY KEY,
    TenLoai VARCHAR(50) NOT NULL UNIQUE,
    GiaTieuChuan DECIMAL(12, 2) NOT NULL,
    SucChuaToiDa INT NOT NULL,
    CONSTRAINT chk_GiaTieuChuan CHECK (GiaTieuChuan > 0),
    CONSTRAINT chk_SucChuaToiDa CHECK (SucChuaToiDa > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Bảng Phòng
CREATE TABLE IF NOT EXISTS Phong (
    MaPhong INT AUTO_INCREMENT PRIMARY KEY,
    TenPhong VARCHAR(10) NOT NULL UNIQUE,
    Tang INT NOT NULL,
    MaLoaiPhong INT NOT NULL,
    TrangThai VARCHAR(20) DEFAULT 'Trong',
    CONSTRAINT fk_Phong_LoaiPhong FOREIGN KEY (MaLoaiPhong) 
        REFERENCES LoaiPhong(MaLoaiPhong) ON DELETE NO ACTION,
    CONSTRAINT chk_TrangThaiPhong CHECK (TrangThai IN ('Trong', 'Dang_O', 'Dang_Don_Dep', 'Bao_Tri'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Bảng Khách Hàng
CREATE TABLE IF NOT EXISTS KhachHang (
    MaKH INT AUTO_INCREMENT PRIMARY KEY,
    HoTen VARCHAR(100) NOT NULL,
    CCCD VARCHAR(15) NOT NULL UNIQUE,
    DienThoai VARCHAR(15) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Bảng Đặt Phòng
CREATE TABLE IF NOT EXISTS DatPhong (
    MaDatPhong INT AUTO_INCREMENT PRIMARY KEY,
    MaKH INT NOT NULL,
    MaPhong INT NOT NULL,
    NgayCheckIn DATE NOT NULL,
    NgayCheckOut DATE NOT NULL,
    TienCoc DECIMAL(12, 2) DEFAULT 0.00,
    TrangThaiDon VARCHAR(20) DEFAULT 'Cho_Duyet',
    ThoiGianTao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_DatPhong_KhachHang FOREIGN KEY (MaKH) 
        REFERENCES KhachHang(MaKH) ON DELETE NO ACTION,
    CONSTRAINT fk_DatPhong_Phong FOREIGN KEY (MaPhong) 
        REFERENCES Phong(MaPhong) ON DELETE NO ACTION,
    CONSTRAINT chk_ThoiGianDat CHECK (NgayCheckOut > NgayCheckIn),
    CONSTRAINT chk_TienCoc CHECK (TienCoc >= 0),
    CONSTRAINT chk_TrangThaiDon CHECK (TrangThaiDon IN ('Cho_Duyet', 'Da_Coc', 'Da_Nhan_Phong', 'Da_Huy', 'Hoan_Thanh'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Bảng Hóa Đơn (Quan hệ 1-1 với DatPhong)
CREATE TABLE IF NOT EXISTS HoaDon (
    MaHoaDon INT AUTO_INCREMENT PRIMARY KEY,
    MaDatPhong INT NOT NULL UNIQUE,
    TienPhong DECIMAL(12, 2) NOT NULL,
    TienDichVu DECIMAL(12, 2) DEFAULT 0.00,
    TongTien DECIMAL(12, 2) NOT NULL,
    NgayThanhToan TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_HoaDon_DatPhong FOREIGN KEY (MaDatPhong) 
        REFERENCES DatPhong(MaDatPhong) ON DELETE NO ACTION,
    CONSTRAINT chk_TienDichVu CHECK (TienDichVu >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ====================================================================
-- CHỈ MỤC TỐI ƯU HIỆU NĂNG (INDEXES)
-- ====================================================================

-- Chỉ mục tối ưu hóa kiểm tra xung đột lịch đặt phòng (Overbooking)
CREATE INDEX IX_DatPhong_Concurrency 
ON DatPhong (MaPhong, NgayCheckIn, NgayCheckOut, TrangThaiDon);

-- Chỉ mục tối ưu hóa tìm kiếm phòng trống theo loại phòng & trạng thái
CREATE INDEX IX_Phong_Status 
ON Phong (MaLoaiPhong, TrangThai);

-- ====================================================================
-- VIEW BÁO CÁO DOANH THU KHOA HỌC (VIEW)
-- JOIN 4 bảng: HoaDon, DatPhong, KhachHang, Phong, LoaiPhong
-- ====================================================================
CREATE OR REPLACE VIEW vw_DoanhThuKhachSan AS
SELECT 
    hd.MaHoaDon,
    hd.MaDatPhong,
    kh.HoTen AS TenKhachHang,
    kh.CCCD,
    p.TenPhong,
    lp.TenLoai AS HangPhong,
    dp.NgayCheckIn,
    dp.NgayCheckOut,
    DATEDIFF(dp.NgayCheckOut, dp.NgayCheckIn) AS SoDemLuuTru,
    hd.TienPhong,
    hd.TienDichVu,
    hd.TongTien,
    hd.NgayThanhToan
FROM HoaDon hd
JOIN DatPhong dp ON hd.MaDatPhong = dp.MaDatPhong
JOIN KhachHang kh ON dp.MaKH = kh.MaKH
JOIN Phong p ON dp.MaPhong = p.MaPhong
JOIN LoaiPhong lp ON p.MaLoaiPhong = lp.MaLoaiPhong;
