# Java 23 统一升级设计

## 目标

将 `services/java-core` 的本地 Maven 编译环境和 Docker 构建、运行环境从 Java 21 统一升级到 Java 23，避免环境版本偏差。

## 变更范围

- 将 `services/java-core/pom.xml` 中的 `java.version` 从 `21` 改为 `23`。
- 将 `services/java-core/Dockerfile` 的 Maven 构建镜像从 Temurin 21 改为 Temurin 23。
- 将同一 Dockerfile 的运行时镜像从 Temurin 21 JRE 改为 Temurin 23 JRE。
- 不修改 Java 源码、依赖版本、服务配置或其他项目。

## 验证

- 检索仓库，确认目标服务不再残留 Java 21 版本声明。
- 确认本机 `java` 和 Maven 使用 Java 23。
- 执行 Maven 构建；若 Docker 可用，再执行 Docker 镜像构建。

本次仅修改构建配置，经用户同意不新增测试，使用真实构建作为验证。
