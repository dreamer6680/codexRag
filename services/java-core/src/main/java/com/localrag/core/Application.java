package com.localrag.core;

import java.time.Instant;
import java.util.List;
import jakarta.persistence.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@SpringBootApplication
public class Application {
  public static void main(String[] args) { SpringApplication.run(Application.class, args); }
}

@Entity
class DocumentRecord {
  @Id @GeneratedValue(strategy = GenerationType.UUID) String id;
  @Column(nullable=false) String name;
  @Column(nullable=false) String contentHash;
  @Column(nullable=false) int version;
  @Column(nullable=false) String status = "queued";
  Instant createdAt = Instant.now();
}
interface DocumentRepository extends JpaRepository<DocumentRecord, String> {
  List<DocumentRecord> findByContentHashOrderByVersionDesc(String contentHash);
}
record CreateDocument(@NotBlank String name, @NotBlank String contentHash) {}
record DocumentView(String id, String name, int version, String status, Instant createdAt) {
  static DocumentView from(DocumentRecord d) { return new DocumentView(d.id, d.name, d.version, d.status, d.createdAt); }
}

@RestController
@RequestMapping("/api/documents")
class DocumentController {
  private final DocumentRepository documents;
  DocumentController(DocumentRepository documents) { this.documents = documents; }
  @GetMapping List<DocumentView> all() { return documents.findAll().stream().map(DocumentView::from).toList(); }
  @PostMapping @ResponseStatus(HttpStatus.CREATED) DocumentView create(@Valid @RequestBody CreateDocument request) {
    var previous = documents.findByContentHashOrderByVersionDesc(request.contentHash());
    if (!previous.isEmpty()) return DocumentView.from(previous.getFirst());
    var d = new DocumentRecord(); d.name = request.name(); d.contentHash = request.contentHash(); d.version = 1;
    return DocumentView.from(documents.save(d));
  }
}

@RestController
class HealthController { @GetMapping("/health") Object health() { return java.util.Map.of("status", "ok"); } }
