#!/usr/bin/env ruby

require "csv"
require "fileutils"
require "json"
require "yaml"

repo_root = File.expand_path("..", __dir__)
citations_path = ENV.fetch("S2_CITATIONS_PATH", "/tmp/s2_citations_contexts.json")
author_paths = Dir[ENV.fetch("S2_AUTHORS_GLOB", "/tmp/s2_authors_*.json")].sort
output_path = File.join(repo_root, "_research", "citation_review.csv")
recovered_path = File.join(repo_root, "_research", "recovered_excerpts.json")
site_excerpts_path = File.join(repo_root, "assets", "data", "citation_excerpts.json")
site_excerpt_summary_path = File.join(repo_root, "_data", "citation_excerpt_summary.yml")
research_use_path = File.join(repo_root, "_data", "research_use.yml")

abort "Missing citation data: #{citations_path}" unless File.exist?(citations_path)
abort "Missing author affiliation batches" if author_paths.empty?

citations = JSON.parse(File.read(citations_path)).fetch("data")
authors = author_paths.flat_map { |path| JSON.parse(File.read(path)) }.compact
authors_by_id = authors.to_h { |author| [author["authorId"], author] }
research_use = YAML.load_file(research_use_path).fetch("llmattacks")
recovered = File.exist?(recovered_path) ? JSON.parse(File.read(recovered_path)) : {}
site_excerpts = []
normalize_publication_url = lambda do |url|
  url.to_s.sub(%r{\Ahttp://}, "https://").sub(%r{#page=1\z}, "").sub(%r{/\z}, "")
end

verified_by_arxiv = Hash.new { |hash, key| hash[key] = [] }
verified_by_title = Hash.new { |hash, key| hash[key] = [] }
organizations_by_url = Hash.new { |hash, key| hash[key] = [] }

research_use.each do |group, organizations|
  Array(organizations).each do |organization|
    record = "#{organization.fetch("name")} (#{group.sub(/s\z/, "")})"
    arxiv_id = organization.fetch("url", "")[%r{arxiv\.org/pdf/([^#?]+)}, 1]
    verified_by_arxiv[arxiv_id] << record if arxiv_id
    verified_by_title[organization.fetch("paper").downcase] << record
    organizations_by_url[normalize_publication_url.call(organization.fetch("url", ""))] << organization.fetch("name")
  end
end

FileUtils.mkdir_p(File.dirname(output_path))

headers = [
  "semantic_scholar_paper_id",
  "title",
  "year",
  "authors",
  "indexed_author_affiliations",
  "external_ids",
  "semantic_scholar_url",
  "open_access_pdf",
  "citing_paper_citation_count",
  "citation_context_count",
  "citation_contexts",
  "excerpt_source_url",
  "excerpt_page",
  "excerpt_recovery_method",
  "is_influential_citation",
  "review_status",
  "primary_source_verified_organizations",
  "selected_for_site",
  "annotation_notes"
]

CSV.open(output_path, "w:UTF-8", write_headers: true, headers: headers, force_quotes: true) do |csv|
  citations.each do |citation|
    paper = citation.fetch("citingPaper")
    paper_authors = Array(paper["authors"])
    affiliations = paper_authors.flat_map do |author|
      Array(authors_by_id.dig(author["authorId"], "affiliations"))
    end.compact.uniq.sort

    external_ids = paper.fetch("externalIds", {})
    arxiv_id = external_ids["ArXiv"]
    verified = Array(verified_by_arxiv[arxiv_id])

    if verified.empty?
      title = paper.fetch("title", "").downcase
      verified = verified_by_title.each_with_object([]) do |(selected_title, records), matches|
        matches.concat(records) if title.include?(selected_title) || selected_title.include?(title)
      end
    end

    contexts = Array(citation["contexts"]).map { |context| context.to_s.gsub(/\s+/, " ").strip }.reject(&:empty?)
    recovered_excerpt = recovered[paper["paperId"]]
    if contexts.empty? && recovered_excerpt
      contexts = [recovered_excerpt.fetch("excerpt").to_s.gsub(/\s+/, " ").strip].reject(&:empty?)
    end

    source_url = recovered_excerpt&.fetch("source_url", "")
    source_url = paper.dig("openAccessPdf", "url").to_s if source_url.to_s.empty?
    arxiv_id = external_ids["ArXiv"] || external_ids["DOI"].to_s[%r{\A10\.48550/arXiv\.(.+)\z}i, 1]
    source_url = "https://arxiv.org/pdf/#{arxiv_id}#page=1" if source_url.to_s.empty? && arxiv_id
    source_url = paper["url"] if source_url.to_s.empty?

    review_status =
      if recovered_excerpt
        recovered_excerpt.fetch("method")
      elsif contexts.empty?
        "metadata_reviewed_no_context"
      else
        "metadata_and_context_reviewed"
      end

    unless contexts.empty?
      site_excerpts << {
        "title" => paper["title"],
        "year" => paper["year"],
        "authors" => paper_authors.map { |author| author["name"] }.compact.join("; "),
        "url" => source_url,
        "excerpt" => contexts.first,
        "page" => recovered_excerpt&.fetch("page", nil),
        "evidence_type" => recovered_excerpt&.fetch("method", "semantic_scholar_context"),
        "organizations" => organizations_by_url[normalize_publication_url.call(source_url)].uniq.sort
      }
    end

    csv << [
      paper["paperId"],
      paper["title"],
      paper["year"],
      paper_authors.map { |author| author["name"] }.compact.join("; "),
      affiliations.join("; "),
      external_ids.sort.map { |key, value| "#{key}:#{value}" }.join("; "),
      paper["url"],
      paper.dig("openAccessPdf", "url"),
      paper["citationCount"],
      contexts.size,
      contexts.join(" || "),
      source_url,
      recovered_excerpt&.fetch("page", nil),
      recovered_excerpt&.fetch("method", "semantic_scholar_context"),
      citation["isInfluential"] == true,
      review_status,
      verified.uniq.sort.join("; "),
      !verified.empty?,
      "Indexed affiliations come from Semantic Scholar author profiles and may not match the paper byline; selected organizations were verified against the citing paper."
    ]
  end
end

FileUtils.mkdir_p(File.dirname(site_excerpts_path))
featured_excerpt_titles = [
  "LogicPoison: Logical Attacks on Graph Retrieval-Augmented Generation",
  "A General Framework for Defending against Query-based Black-box Attacks on Neural Network Models"
]
lavish_excerpt_score = lambda do |record|
  excerpt = record.fetch("excerpt", "").downcase.tr("‐‑–—", "----")
  normalized = excerpt.gsub("-", " ").gsub(/\s+/, " ")
  usage_phrase = "(?:widely\\s+used|widely\\s+adopted|commonly\\s+used|commonly\\s+adopted)"
  method_language = "(?:metric|defen\\w*|technique\\w*|strateg\\w*|baseline\\w*|filter\\w*)"
  direct_usage = /
    (?:perplexity|\bppl\b).{0,100}#{usage_phrase}|
    #{usage_phrase}.{0,40}#{method_language}.{0,100}(?:perplexity|\bppl\b)
  /x
  standard_usage = /
    (?:perplexity|\bppl\b).{0,100}(?:standard|strong|popular|representative).{0,50}#{method_language}|
    (?:standard|strong|popular|representative).{0,50}#{method_language}.{0,100}(?:perplexity|\bppl\b)
  /x
  (normalized.match?(direct_usage) ? 100 : 0) +
    (normalized.match?(standard_usage) ? 50 : 0)
end
site_excerpts.sort_by! do |record|
  featured_index = featured_excerpt_titles.index(record.fetch("title", ""))
  [
    featured_index || featured_excerpt_titles.size,
    -lavish_excerpt_score.call(record),
    -record.fetch("year", 0).to_i,
    record.fetch("title", "")
  ]
end
File.write(site_excerpts_path, JSON.pretty_generate({ "llmattacks" => site_excerpts }) + "\n")
File.write(
  site_excerpt_summary_path,
  {
    "llmattacks" => {
      "count" => site_excerpts.size,
      "url" => "/assets/data/citation_excerpts.json"
    }
  }.to_yaml
)

puts "Wrote #{citations.size} citation records to #{output_path}"
puts "Wrote #{site_excerpts.size} citation excerpts to #{site_excerpts_path}"
