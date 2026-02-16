from llama_cpp import Llama
import time


model_path = r"C:\Users\hp\Desktop\RAG_ChatBot\models\Llama-3.2-3B-Instruct-UD-Q6_K_XL.gguf"
# model_path = "chat.nextgen"
model_path = "Mistral-7B-Instruct-v0.3.Q4_K_M.gguf"

start_time = time.time()
llm = Llama(
        model_path=model_path,
        n_gpu_layers=-1, 
        n_ctx=4096,
        chat_format="mistral", #llama-3, qwen, mistral
        verbose=False
    )
end_time = time.time()
print(f"Time taken to load model: {end_time-start_time}")


prompt = """
Rewrite the following text in clear, simple language.
Keep all important information.
Do not shorten it too much.

Artificial intelligence has rapidly transitioned from a niche academic pursuit into a foundational technology influencing nearly every major industry. Early research in AI focused on symbolic reasoning and rule-based systems, which were limited by their inability to generalize beyond narrowly defined problems. Over time, advances in statistical methods, increased computational power, and the availability of large datasets enabled a shift toward machine learning approaches, particularly neural networks.

The resurgence of neural networks in the early 2010s, often referred to as the deep learning revolution, was driven by breakthroughs in image recognition, natural language processing, and speech recognition. These systems demonstrated that models trained on massive datasets could outperform traditional algorithms in tasks that were once considered uniquely human. As a result, AI adoption accelerated across sectors such as healthcare, finance, transportation, and entertainment.

In healthcare, AI systems are now used to assist with medical imaging analysis, drug discovery, and patient risk prediction. While these tools offer the potential to improve diagnostic accuracy and reduce costs, they also raise concerns about data privacy, bias, and accountability. Clinical decisions informed by opaque algorithms challenge existing regulatory frameworks and ethical norms, prompting calls for greater transparency and oversight.

The financial sector has similarly embraced AI for fraud detection, algorithmic trading, credit scoring, and customer service automation. These applications increase efficiency and scalability but can also amplify systemic risks if poorly designed models behave unpredictably under novel market conditions. Regulatory bodies have begun to scrutinize AI-driven financial systems to ensure stability and fairness.

Transportation has been transformed by AI through the development of advanced driver-assistance systems and autonomous vehicles. While fully autonomous transportation promises reductions in accidents and congestion, real-world deployment has proven more complex than initially anticipated. Technical limitations, edge cases, and legal liability issues continue to slow widespread adoption.

Beyond specific industries, AI has broader societal implications. Automation threatens to displace certain categories of jobs while simultaneously creating new roles that require different skill sets. This labor transition places pressure on educational systems and workforce training programs to adapt more rapidly than in previous technological shifts. Policymakers face the challenge of balancing innovation with social stability.

Ethical considerations are increasingly central to discussions about AI deployment. Issues such as algorithmic bias, surveillance, misinformation, and the concentration of power among a small number of technology companies have sparked public debate. Many researchers and organizations advocate for the development of ethical guidelines and governance frameworks to ensure AI benefits are distributed equitably.

Looking ahead, AI research continues to explore more general and adaptable systems, including advances in reinforcement learning, multimodal models, and alignment techniques. While speculative visions of artificial general intelligence remain uncertain, incremental progress continues to expand the scope of what AI systems can do. The long-term impact of AI will depend not only on technical capabilities but also on the social, legal, and ethical choices made alongside their development.

"""

start_time = time.time()
output = llm.create_completion(
        prompt=prompt,
    )
end_time = time.time()
print(f"Time taken to respond: {end_time-start_time}")

response = output['choices'][0]['text'].strip().lower()

print(response)