-- Chơi thử mở rộng: thêm Lotto 5/35, Max 3D, Max 3D Pro. Ràng buộc cột game ở 015 không đặt tên nên Postgres đặt mặc định.
ALTER TABLE play_tickets DROP CONSTRAINT IF EXISTS play_tickets_game_check;
ALTER TABLE play_tickets ADD CONSTRAINT play_tickets_game_check
  CHECK (game IN ('xs', 'power655', 'mega645', 'lotto535', 'max3d', 'max3dpro'));
