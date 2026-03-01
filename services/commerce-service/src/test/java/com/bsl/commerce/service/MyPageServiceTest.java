package com.bsl.commerce.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.repository.MyPageRepository;
import com.bsl.commerce.repository.OrderRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class MyPageServiceTest {

    @Mock
    private MyPageRepository myPageRepository;

    @Mock
    private CatalogService catalogService;

    @Mock
    private SupportTicketService supportTicketService;

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private LoyaltyPointService loyaltyPointService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private MyPageService newService() {
        return new MyPageService(
            myPageRepository,
            catalogService,
            supportTicketService,
            orderRepository,
            loyaltyPointService,
            objectMapper
        );
    }

    @Test
    void addCommentRejectsWhenOrderStatusNotDelivered() {
        MyPageService service = newService();
        when(orderRepository.findOrderById(12L)).thenReturn(
            Map.of("order_id", 12L, "user_id", 1L, "status", "PAID")
        );

        assertThatThrownBy(() -> service.addComment(1L, new MyPageService.CommentCreateRequest(12L, "제목", 5, "좋아요")))
            .isInstanceOf(ApiException.class)
            .satisfies(error -> {
                ApiException apiException = (ApiException) error;
                assertThat(apiException.getCode()).isEqualTo("invalid_order_status");
            });
    }

    @Test
    void addCommentCreatesEntryForDeliveredOrder() {
        MyPageService service = newService();

        when(orderRepository.findOrderById(99L)).thenReturn(
            Map.of("order_id", 99L, "user_id", 1L, "status", "DELIVERED")
        );
        when(myPageRepository.existsCommentByUserAndOrder(1L, 99L)).thenReturn(false);
        when(myPageRepository.insertComment(1L, 99L, "샘플 도서", 4, "배송이 빨랐습니다.")).thenReturn(501L);

        Map<String, Object> inserted = Map.of(
            "comment_id", 501L,
            "order_id", 99L,
            "title", "샘플 도서",
            "rating", 4,
            "content", "배송이 빨랐습니다.",
            "created_at", Timestamp.from(Instant.parse("2026-02-24T03:30:00Z"))
        );
        when(myPageRepository.findCommentById(501L)).thenReturn(inserted);

        Map<String, Object> result = service.addComment(
            1L,
            new MyPageService.CommentCreateRequest(99L, "샘플 도서", 4, "배송이 빨랐습니다.")
        );

        assertThat(result.get("orderId")).isEqualTo(99L);
        assertThat(result.get("rating")).isEqualTo(4);
        assertThat(result.get("content")).isEqualTo("배송이 빨랐습니다.");
        assertThat(result.get("createdAt")).isEqualTo("2026-02-24T03:30:00Z");
    }

    @Test
    void listInquiriesMapsSupportTicketToMyPageShape() {
        MyPageService service = newService();

        when(supportTicketService.listTicketsForUser(1L, 100)).thenReturn(
            List.of(
                Map.of(
                    "ticket_id", 44L,
                    "summary", "환불 상태 문의",
                    "category", "REFUND",
                    "status", "IN_PROGRESS",
                    "detail_json", "{\"content\":\"환불 처리 현황을 알고 싶습니다.\"}",
                    "created_at", Timestamp.from(Instant.parse("2026-02-24T01:00:00Z"))
                )
            )
        );

        List<Map<String, Object>> inquiries = service.listInquiries(1L);

        assertThat(inquiries).hasSize(1);
        Map<String, Object> inquiry = inquiries.get(0);
        assertThat(inquiry.get("id")).isEqualTo("44");
        assertThat(inquiry.get("category")).isEqualTo("결제/환불");
        assertThat(inquiry.get("status")).isEqualTo("처리 중");
        assertThat(inquiry.get("content")).isEqualTo("환불 처리 현황을 알고 싶습니다.");
    }
}
