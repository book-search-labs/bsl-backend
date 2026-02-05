package com.bsl.commerce.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "commerce")
public class CommerceProperties {
    private Cart cart = new Cart();
    private Inventory inventory = new Inventory();

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

    public static class Cart {
        private int maxQtyPerItem = 20;
        private int maxDistinctItems = 200;

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
}
