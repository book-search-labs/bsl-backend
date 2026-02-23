package com.bsl.commerce.api;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.common.RequestUtils;
import com.bsl.commerce.repository.AddressRepository;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.transaction.annotation.Transactional;

@RestController
@RequestMapping("/api/v1")
public class AddressController {
    private final AddressRepository addressRepository;

    public AddressController(AddressRepository addressRepository) {
        this.addressRepository = addressRepository;
    }

    @GetMapping("/addresses")
    public Map<String, Object> listAddresses(@RequestHeader(value = "x-user-id", required = false) String userIdHeader) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> items = addressRepository.listAddresses(userId);
        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        return response;
    }

    @PostMapping("/addresses")
    @Transactional
    public Map<String, Object> createAddress(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @RequestBody AddressRequest request
    ) {
        if (request == null || request.name == null || request.phone == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "받는 분 이름과 연락처는 필수입니다.");
        }
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        if (Boolean.TRUE.equals(request.isDefault)) {
            addressRepository.clearDefault(userId);
        }
        long addressId = addressRepository.insertAddress(
            userId,
            request.name,
            request.phone,
            request.zip,
            request.addr1,
            request.addr2,
            Boolean.TRUE.equals(request.isDefault)
        );
        Map<String, Object> address = addressRepository.findAddress(addressId);
        Map<String, Object> response = base();
        response.put("address", address);
        return response;
    }

    @PostMapping("/addresses/{addressId}/default")
    @Transactional
    public Map<String, Object> setDefault(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @PathVariable long addressId
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> address = addressRepository.findAddress(addressId);
        if (address == null || com.bsl.commerce.common.JdbcUtils.asLong(address.get("user_id")) != userId) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "배송지를 찾을 수 없습니다.");
        }
        addressRepository.clearDefault(userId);
        addressRepository.setDefault(addressId);
        Map<String, Object> response = base();
        response.put("address", addressRepository.findAddress(addressId));
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

    public static class AddressRequest {
        public String name;
        public String phone;
        public String zip;
        public String addr1;
        public String addr2;
        public Boolean isDefault;
    }
}
