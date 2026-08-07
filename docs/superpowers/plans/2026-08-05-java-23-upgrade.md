# Java 23 Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Java Core service's Maven, Docker build, and Docker runtime Java baseline from version 21 to version 23.

**Architecture:** Keep the existing Spring Boot application and container build structure unchanged. Update only the three explicit Java-version declarations so local and containerized builds use the same Java release.

**Tech Stack:** Java 23, Maven, Spring Boot 3.4.5, Eclipse Temurin container images, Docker

## Global Constraints

- Modify only `services/java-core/pom.xml` and `services/java-core/Dockerfile`.
- Do not change Java source code, dependencies, service configuration, or other projects.
- Use Java 23 for Maven compilation, the Docker build stage, and the Docker runtime stage.
- This configuration-only change is exempt from adding a test; verify it with searches and real builds.

---

### Task 1: Align the Java Core service on Java 23

**Files:**
- Modify: `services/java-core/pom.xml:4`
- Modify: `services/java-core/Dockerfile:1`
- Modify: `services/java-core/Dockerfile:7`

**Interfaces:**
- Consumes: the existing Spring Boot 3.4.5 Maven project and multi-stage Docker build.
- Produces: Maven bytecode targeting Java 23 and a Java 23 container build/runtime environment.

- [ ] **Step 1: Capture the pre-change version declarations**

Run:

```powershell
rg -n "java.version|temurin[:-](21|23)" services/java-core/pom.xml services/java-core/Dockerfile
```

Expected: one `java.version` value of `21` and two Temurin 21 image references.

- [ ] **Step 2: Update Maven and Docker version declarations**

Set the Maven property to:

```xml
<properties><java.version>23</java.version></properties>
```

Set the Docker image declarations to:

```dockerfile
FROM maven:3.9-eclipse-temurin-23 AS build
FROM eclipse-temurin:23-jre
```

- [ ] **Step 3: Verify the version declarations**

Run:

```powershell
rg -n "java.version|temurin[:-](21|23)" services/java-core/pom.xml services/java-core/Dockerfile
```

Expected: `java.version` is `23`, both image references use Temurin 23, and no Temurin 21 reference remains.

- [ ] **Step 4: Verify the local toolchain and Maven build**

Run:

```powershell
java -version
mvn -version
mvn -f services/java-core/pom.xml clean package -DskipTests
```

Expected: Java and Maven report Java 23, and Maven exits with code 0 and `BUILD SUCCESS`.

- [ ] **Step 5: Verify the Docker build when Docker is available**

Run:

```powershell
docker build -t rag-java-core:java23 services/java-core
```

Expected: Docker exits with code 0 and creates `rag-java-core:java23` using Java 23 build and runtime images.

- [ ] **Step 6: Review the final diff**

Run:

```powershell
rg -n "java.version|temurin[:-](21|23)" services/java-core/pom.xml services/java-core/Dockerfile
rg -n "java.version>21|temurin[:-]21" services/java-core/pom.xml services/java-core/Dockerfile
```

Expected: the first command shows exactly three Java 23 declarations and the second command has no matches. The service directory is currently untracked, so Git cannot provide a meaningful file diff.
