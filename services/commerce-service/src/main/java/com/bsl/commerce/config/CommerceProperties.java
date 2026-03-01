package com.bsl.commerce.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "commerce")
public class CommerceProperties {
    private Cart cart = new Cart();
    private Inventory inventory = new Inventory();
    private Loyalty loyalty = new Loyalty();

    public Cart getCart() {
        return cart;
    }

    public void setCart(Cart cart) {
        this.cart = cart;
    }

    public Inventory getInventory() {
        return inventory;
    }

    public void setInventory(Inventory inventory) {
        this.inventory = inventory;
    }

    public Loyalty getLoyalty() {
        return loyalty;
    }

    public void setLoyalty(Loyalty loyalty) {
        this.loyalty = loyalty;
    }

    public static class Cart {
        private int maxQtyPerItem = 20;
        private int maxDistinctItems = 200;
        private int freeShippingThreshold = 20000;
        private int bonusPointThreshold = 50000;
        private int baseShippingFee = 3000;
        private int fastShippingFee = 5000;

        public int getMaxQtyPerItem() {
            return maxQtyPerItem;
        }

        public void setMaxQtyPerItem(int maxQtyPerItem) {
            this.maxQtyPerItem = maxQtyPerItem;
        }

        public int getMaxDistinctItems() {
            return maxDistinctItems;
        }

        public void setMaxDistinctItems(int maxDistinctItems) {
            this.maxDistinctItems = maxDistinctItems;
        }

        public int getFreeShippingThreshold() {
            return freeShippingThreshold;
        }

        public void setFreeShippingThreshold(int freeShippingThreshold) {
            this.freeShippingThreshold = freeShippingThreshold;
        }

        public int getBonusPointThreshold() {
            return bonusPointThreshold;
        }

        public void setBonusPointThreshold(int bonusPointThreshold) {
            this.bonusPointThreshold = bonusPointThreshold;
        }

        public int getBaseShippingFee() {
            return baseShippingFee;
        }

        public void setBaseShippingFee(int baseShippingFee) {
            this.baseShippingFee = baseShippingFee;
        }

        public int getFastShippingFee() {
            return fastShippingFee;
        }

        public void setFastShippingFee(int fastShippingFee) {
            this.fastShippingFee = fastShippingFee;
        }
    }

    public static class Inventory {
        private long defaultSellerId = 1L;

        public long getDefaultSellerId() {
            return defaultSellerId;
        }

        public void setDefaultSellerId(long defaultSellerId) {
            this.defaultSellerId = defaultSellerId;
        }
    }

    public static class Loyalty {
        private int earnRatePercent = 5;

        public int getEarnRatePercent() {
            return earnRatePercent;
        }

        public void setEarnRatePercent(int earnRatePercent) {
            this.earnRatePercent = earnRatePercent;
        }
    }
}
