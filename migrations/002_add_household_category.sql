-- 002_add_household_category.sql — Add "Быт" (household goods) category

-- Shift sort_order for categories that will come after "Быт"
UPDATE categories SET sort_order = sort_order + 1 WHERE sort_order >= 8;

-- Insert new category between Одежда (7) and Развлечения (now 9)
INSERT OR IGNORE INTO categories (name, icon, sort_order) VALUES
    ('Быт', '🧹', 8);
