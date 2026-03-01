UPDATE offer
SET
  list_price = GREATEST((list_price DIV 100) * 100, 0),
  sale_price = GREATEST((sale_price DIV 100) * 100, 0)
WHERE MOD(list_price, 100) <> 0
   OR MOD(sale_price, 100) <> 0;

UPDATE cart_item
SET unit_price = GREATEST((unit_price DIV 100) * 100, 0)
WHERE unit_price IS NOT NULL
  AND MOD(unit_price, 100) <> 0;
