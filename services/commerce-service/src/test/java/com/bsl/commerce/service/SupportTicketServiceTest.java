package com.bsl.commerce.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.repository.OrderRepository;
import com.bsl.commerce.repository.SupportTicketRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class SupportTicketServiceTest {

    @Mock
    private SupportTicketRepository supportTicketRepository;

    @Mock
    private OrderRepository orderRepository;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private SupportTicketService newService() {
        return new SupportTicketService(supportTicketRepository, orderRepository, objectMapper);
    }

    @Test
    void createTicketAllowsOwnedOrderAndReturnsCreatedTicket() {
        SupportTicketService service = newService();

        when(orderRepository.findOrderById(99L)).thenReturn(Map.of("order_id", 99L, "user_id", 7L));
        when(supportTicketRepository.insertTicket(any(), eq(7L), eq(99L), eq("ORDER"), eq("HIGH"), eq("RECEIVED"),
            eq("주문 결제가 실패했습니다"), any(), eq("PAYMENT_FAILED"), eq("sess-1"), eq("req-1"), any()))
            .thenReturn(501L);
        when(supportTicketRepository.findTicketById(501L)).thenReturn(
            Map.of(
                "ticket_id", 501L,
                "ticket_no", "STK202602230001",
                "user_id", 7L,
                "status", "RECEIVED",
                "severity", "HIGH"
            )
        );

        Map<String, Object> created = service.createTicket(
            7L,
            new SupportTicketService.TicketCreateRequest(
                99L,
                "ORDER",
                "HIGH",
                "주문 결제가 실패했습니다",
                Map.of("pg", "MOCK"),
                "PAYMENT_FAILED",
                "sess-1",
                "req-1"
            )
        );

        assertThat(created).containsEntry("ticket_id", 501L);
        assertThat(created).containsEntry("status", "RECEIVED");
        verify(supportTicketRepository).insertTicketEvent(eq(501L), eq("TICKET_RECEIVED"), eq(null), eq("RECEIVED"), eq("ticket created"), any());
    }

    @Test
    void createTicketRejectsOrderOfDifferentUser() {
        SupportTicketService service = newService();

        when(orderRepository.findOrderById(77L)).thenReturn(Map.of("order_id", 77L, "user_id", 9L));

        assertThatThrownBy(() -> service.createTicket(
            1L,
            new SupportTicketService.TicketCreateRequest(
                77L,
                "ORDER",
                "HIGH",
                "다른 사용자 주문 접근",
                Map.of(),
                null,
                "sess-2",
                "req-2"
            )
        ))
            .isInstanceOf(ApiException.class)
            .satisfies(error -> assertThat(((ApiException) error).getCode()).isEqualTo("forbidden"));
    }

    @Test
    void getTicketByNoForUserRejectsForeignOwner() {
        SupportTicketService service = newService();

        when(supportTicketRepository.findTicketByNo("STK202602230002")).thenReturn(
            Map.of(
                "ticket_id", 700L,
                "ticket_no", "STK202602230002",
                "user_id", 88L,
                "status", "IN_PROGRESS",
                "severity", "MEDIUM"
            )
        );

        assertThatThrownBy(() -> service.getTicketByNoForUser(1L, "STK202602230002"))
            .isInstanceOf(ApiException.class)
            .satisfies(error -> assertThat(((ApiException) error).getCode()).isEqualTo("forbidden"));
    }

    @Test
    void updateStatusAsAdminPersistsTransition() {
        SupportTicketService service = newService();

        Map<String, Object> received = Map.of(
            "ticket_id", 901L,
            "ticket_no", "STK202602230003",
            "user_id", 1L,
            "status", "RECEIVED",
            "severity", "MEDIUM"
        );
        Map<String, Object> inProgress = Map.of(
            "ticket_id", 901L,
            "ticket_no", "STK202602230003",
            "user_id", 1L,
            "status", "IN_PROGRESS",
            "severity", "MEDIUM"
        );
        when(supportTicketRepository.findTicketById(901L)).thenReturn(received, inProgress);

        Map<String, Object> updated = service.updateStatusAsAdmin(901L, "in_progress", "담당자 배정 완료");

        assertThat(updated).containsEntry("status", "IN_PROGRESS");
        verify(supportTicketRepository).updateStatus(eq(901L), eq("IN_PROGRESS"), isNull());
        verify(supportTicketRepository).insertTicketEvent(eq(901L), eq("STATUS_CHANGED"), eq("RECEIVED"), eq("IN_PROGRESS"), eq("담당자 배정 완료"), any());
    }

    @Test
    void listTicketsForUserClampsLimit() {
        SupportTicketService service = newService();

        when(supportTicketRepository.listTicketsByUser(3L, 100)).thenReturn(List.of(Map.of("ticket_id", 1L)));

        List<Map<String, Object>> tickets = service.listTicketsForUser(3L, 1000);

        assertThat(tickets).hasSize(1);
        verify(supportTicketRepository).listTicketsByUser(3L, 100);
    }
}
