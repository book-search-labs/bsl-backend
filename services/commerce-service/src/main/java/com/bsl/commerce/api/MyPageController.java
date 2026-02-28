package com.bsl.commerce.api;

import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.common.RequestUtils;
import com.bsl.commerce.service.MyPageService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/my")
public class MyPageController {
    private final MyPageService myPageService;

    public MyPageController(MyPageService myPageService) {
        this.myPageService = myPageService;
    }

    @GetMapping("/wishlist")
    public Map<String, Object> listWishlist(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> items = myPageService.listWishlist(userId);
        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        return response;
    }

    @PostMapping("/wishlist")
    public Map<String, Object> addWishlist(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @RequestBody WishlistRequest request
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> item = myPageService.addWishlist(userId, request.docId);
        Map<String, Object> response = base();
        response.put("item", item);
        return response;
    }

    @DeleteMapping("/wishlist/{docId}")
    public Map<String, Object> removeWishlist(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @PathVariable String docId
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> items = myPageService.removeWishlist(userId, docId);
        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        return response;
    }

    @GetMapping("/comments")
    public Map<String, Object> listComments(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> items = myPageService.listComments(userId);
        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        return response;
    }

    @PostMapping("/comments")
    public Map<String, Object> addComment(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @RequestBody CommentRequest request
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> item = myPageService.addComment(
            userId,
            new MyPageService.CommentCreateRequest(request.orderId, request.title, request.rating, request.content)
        );
        Map<String, Object> response = base();
        response.put("item", item);
        return response;
    }

    @GetMapping("/wallet/points")
    public Map<String, Object> listPoints(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> wallet = myPageService.getWalletPoints(userId);
        Map<String, Object> response = base();
        response.put("balance", wallet.get("balance"));
        response.put("items", wallet.get("items"));
        return response;
    }

    @GetMapping("/wallet/vouchers")
    public Map<String, Object> listVouchers(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> items = myPageService.listVouchers(userId);
        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        return response;
    }

    @GetMapping("/wallet/coupons")
    public Map<String, Object> listCoupons(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> items = myPageService.listCoupons(userId);
        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        return response;
    }

    @GetMapping("/elib")
    public Map<String, Object> listELibrary(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> items = myPageService.listELibraryBooks(userId);
        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        return response;
    }

    @GetMapping("/notifications")
    public Map<String, Object> listNotifications(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @RequestParam(name = "category", required = false) String category,
        @RequestParam(name = "unreadOnly", required = false, defaultValue = "false") boolean unreadOnly
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> items = myPageService.listNotifications(userId, category, unreadOnly);
        long unreadCount = items.stream().filter(item -> !Boolean.TRUE.equals(item.get("read"))).count();

        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        response.put("unread_count", unreadCount);
        return response;
    }

    @PostMapping("/notifications/{notificationId}/read")
    public Map<String, Object> markNotificationRead(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @PathVariable String notificationId
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        myPageService.markNotificationRead(userId, notificationId);

        Map<String, Object> response = base();
        response.put("ok", true);
        return response;
    }

    @PostMapping("/notifications/read-all")
    public Map<String, Object> markAllNotificationsRead(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        int updated = myPageService.markAllNotificationsRead(userId);

        Map<String, Object> response = base();
        response.put("updated", updated);
        response.put("ok", true);
        return response;
    }

    @GetMapping("/notification-preferences")
    public Map<String, Object> listNotificationPreferences(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> items = myPageService.listNotificationPreferences(userId);

        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        return response;
    }

    @PostMapping("/notification-preferences/{category}")
    public Map<String, Object> setNotificationPreference(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @PathVariable String category,
        @RequestBody NotificationPreferenceRequest request
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> items = myPageService.setNotificationPreference(userId, category, request.enabled);

        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        return response;
    }

    @GetMapping("/gifts")
    public Map<String, Object> listGifts(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> items = myPageService.listGifts(userId);

        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        return response;
    }

    @GetMapping("/gifts/{giftId}")
    public Map<String, Object> getGift(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @PathVariable String giftId
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> item = myPageService.getGiftById(userId, giftId);

        Map<String, Object> response = base();
        response.put("item", item);
        return response;
    }

    @GetMapping("/inquiries")
    public Map<String, Object> listInquiries(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> items = myPageService.listInquiries(userId);

        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        return response;
    }

    @PostMapping("/inquiries")
    public Map<String, Object> createInquiry(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @RequestBody InquiryRequest request
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> item = myPageService.createInquiry(
            userId,
            new MyPageService.InquiryCreateRequest(request.title, request.category, request.content)
        );

        Map<String, Object> response = base();
        response.put("item", item);
        return response;
    }

    private Map<String, Object> base() {
        RequestContext context = RequestContextHolder.get();
        Map<String, Object> response = new HashMap<>();
        response.put("version", "v1");
        response.put("trace_id", context == null ? null : context.getTraceId());
        response.put("request_id", context == null ? null : context.getRequestId());
        return response;
    }

    public static class WishlistRequest {
        public String docId;
        public String title;
        public String author;
        public String coverUrl;
        public Integer price;
    }

    public static class CommentRequest {
        public Long orderId;
        public String title;
        public int rating;
        public String content;
    }

    public static class InquiryRequest {
        public String title;
        public String category;
        public String content;
    }

    public static class NotificationPreferenceRequest {
        public boolean enabled;
    }
}
