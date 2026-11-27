-- Lịch quay Vietlott Max 3D (thứ Hai, Tư, Sáu) và Max 3D Pro (thứ Ba, Năm, Bảy), cùng lúc 18:00.
-- Dùng cho đồng hồ đếm ngược trên trang Vietlott và để planner lập kỳ. Vùng max3d/max3dpro không có khung theo dõi
-- trong WINDOWS nên kỳ chưa có kết quả không sinh cảnh báo "quá giờ".
INSERT INTO draw_schedules (province_code, iso_weekday, draw_time, valid_from)
SELECT v.code, v.wd, '18:00', '2017-01-01'
  FROM (VALUES ('max3d', 1), ('max3d', 3), ('max3d', 5), ('max3dpro', 2), ('max3dpro', 4), ('max3dpro', 6)) AS v(code, wd)
 WHERE EXISTS (SELECT 1 FROM provinces p WHERE p.code = v.code)
   AND NOT EXISTS (SELECT 1 FROM draw_schedules s WHERE s.province_code = v.code AND s.iso_weekday = v.wd);
