package com.bsl.olaploader.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "olap.topics")
public class OlapTopicProperties {
    private String searchImpression = "search_impression_v1";
    private String searchClick = "search_click_v1";
    private String searchDwell = "search_dwell_v1";
    private String acImpression = "ac_impression_v1";
    private String acSelect = "ac_select_v1";

    public String getSearchImpression() {
        return searchImpression;
    }

    public void setSearchImpression(String searchImpression) {
        this.searchImpression = searchImpression;
    }

    public String getSearchClick() {
        return searchClick;
    }

    public void setSearchClick(String searchClick) {
        this.searchClick = searchClick;
    }

    public String getSearchDwell() {
        return searchDwell;
    }

    public void setSearchDwell(String searchDwell) {
        this.searchDwell = searchDwell;
    }

    public String getAcImpression() {
        return acImpression;
    }

    public void setAcImpression(String acImpression) {
        this.acImpression = acImpression;
    }

    public String getAcSelect() {
        return acSelect;
    }

    public void setAcSelect(String acSelect) {
        this.acSelect = acSelect;
    }
}
