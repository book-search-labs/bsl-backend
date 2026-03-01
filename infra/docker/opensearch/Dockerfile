FROM opensearchproject/opensearch:2.11.1

# Required analyzers for books/ac v2 mappings.
RUN /usr/share/opensearch/bin/opensearch-plugin install --batch analysis-nori
RUN /usr/share/opensearch/bin/opensearch-plugin install --batch analysis-icu
