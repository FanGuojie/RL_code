import tensorflow as tf
import numpy as np
import gym
import matplotlib.pyplot as plt
import time
RENDER = False
C_UPDATE_STEPS = 10
A_UPDATE_STEPS = 10
#利用当前策略进行采样，产生数据
class Sample():
    def __init__(self,env, policy_net):
        self.env = env
        self.gamma = 0.90
        self.brain = policy_net
    def sample_steps(self, observation,number_datas,done):
        obs = []
        actions = []
        rs = []
        current_observation = observation
        i = 0
        sum_r = 0
        while i<number_datas and done==False:
            # env.render()
            state = np.reshape(current_observation, [1, 3])
            action = self.brain.choose_action(state)
            # print("action",action)
            observation_, reward, done, info = self.env.step(action)
            sum_r+=reward
            # 存储当前观测
            obs.append(np.reshape(current_observation, [1, 3])[0, :])
            actions.append(action)
            # 存储立即回报
            rs.append((reward+8)/8)
            #推进一步
            current_observation = observation_
            # time.sleep(0.01)
            i = i+1
        # 处理回报
        reward_sum = self.brain.get_v(np.reshape(current_observation,[1,3]))[0,0]
        # print("reward_sum",reward_sum)
        discouted_sum_reward = np.zeros_like(rs)
        for t in reversed(range(0, len(rs))):
            reward_sum = reward_sum * self.gamma + rs[t]
            discouted_sum_reward[t] = reward_sum
        obs = np.reshape(obs, [len(obs), self.brain.n_features])
        actions = np.reshape(actions, [len(actions),1])
        discouted_sum_reward = np.reshape(discouted_sum_reward,[len(discouted_sum_reward),1])
        # print("discouted_sum_reward",discouted_sum_reward)
        return obs, actions, discouted_sum_reward, done,current_observation,sum_r
#定义策略网络
class Policy_Net():
    def __init__(self, env, action_bound, lr = 0.0001, model_file=None):
        # 5. tf工程
        self.sess = tf.Session()
        self.learning_rate = lr
        #输入特征的维数
        self.n_features = env.observation_space.shape[0]
        #输出动作空间的维数
        self.n_actions = 1
        #1.1 输入层
        self.obs = tf.placeholder(tf.float32, shape=[None, self.n_features])
        self.pi, self.pi_params = self.build_a_net('pi', trainable=True)
        self.oldpi, self.oldpi_params = self.build_a_net('oldpi', trainable=False)
        print("action_bound",action_bound[0],action_bound[1])
        self.action = tf.clip_by_value(tf.squeeze(self.pi.sample(1),axis=0), action_bound[0], action_bound[1])
        #定义新旧参数的替换操作
        self.update_oldpi_op = [oldp.assign(p) for p,oldp in zip(self.pi_params, self.oldpi_params)]
        #1.5 当前动作，输入为当前动作，delta,
        self.current_act = tf.placeholder(tf.float32, [None,1])
        #优势函数
        self.adv = tf.placeholder(tf.float32, [None,1])
        #2. 构建损失函数
        ratio = self.pi.prob(self.current_act)/self.oldpi.prob(self.current_act)
        #替代函数
        surr = ratio*self.adv
        self.a_loss = -tf.reduce_mean(tf.minimum(surr,tf.clip_by_value(ratio, 1.0-0.2, 1.0+0.2)*self.adv))
        # self.loss += 0.01*self.normal_dist.entropy()
        #3. 定义一个动作优化器
        self.a_train_op = tf.train.AdamOptimizer(self.learning_rate).minimize(self.a_loss)
        #4.定义critic网络
        self.c_f1 = tf.layers.dense(inputs=self.obs, units=100, activation=tf.nn.relu)
        self.v = tf.layers.dense(inputs=self.c_f1, units=1)
        #定义critic网络的损失函数,输入为td目标
        self.td_target = tf.placeholder(tf.float32, [None,1])
        self.c_loss = tf.reduce_mean(tf.square(self.td_target-self.v))
        self.c_train_op = tf.train.AdamOptimizer(0.0002).minimize(self.c_loss)
        #6. 初始化图中的变量
        self.sess.run(tf.global_variables_initializer())
        #7.定义保存和恢复模型
        self.saver = tf.train.Saver()
        if model_file is not None:
            self.restore_model(model_file)
    def build_a_net(self, name, trainable):
        with tf.variable_scope(name):
            # 1.2.策略网络第一层隐含层
            self.a_f1 = tf.layers.dense(inputs=self.obs, units=100, activation=tf.nn.relu,trainable=trainable)
            # 1.3 第二层，均值
            a_mu = 2*tf.layers.dense(inputs=self.a_f1, units=self.n_actions, activation=tf.nn.tanh,trainable=trainable)
            # 1.3 第二层，标准差
            a_sigma = tf.layers.dense(inputs=self.a_f1, units=self.n_actions, activation=tf.nn.softplus,trainable=trainable)

            # a_mu = 2 * a_mu
            a_sigma = a_sigma
            # 定义带参数的正态分布
            normal_dist = tf.contrib.distributions.Normal(a_mu, a_sigma)
            # 根据正态分布采样一个动作
        params = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope=name)
        return normal_dist, params
    def get_v(self, state):
        v = self.sess.run(self.v, {self.obs:state})
        return v
    #依概率选择动作
    def choose_action(self, state):
        action = self.sess.run(self.action, {self.obs:state})
        # print("greedy action",action)
        return action[0]
    #定义训练
    def train_step(self, state, label, reward):
        #更新旧的策略网络
        self.sess.run(self.update_oldpi_op)
        td_target = reward
        # print("reward",reward)
        delta = td_target - self.sess.run(self.v, feed_dict={self.obs:state})
        # print("delta",delta.shape)
        delta = np.reshape(delta,[len(delta),1])
        for _ in range(A_UPDATE_STEPS):
            self.sess.run([self.a_loss, self.a_train_op], feed_dict={self.obs:state, self.current_act:label, self.adv:delta})
        for _ in range(C_UPDATE_STEPS):
            self.sess.run([self.c_loss, self.c_train_op], feed_dict={self.obs: state, self.td_target: td_target})
        # return a_loss, c_loss
    #定义存储模型函数
    def save_model(self, model_path):
        self.saver.save(self.sess, model_path)
    #定义恢复模型函数
    def restore_model(self, model_path):
        self.saver.restore(self.sess, model_path)
def policy_train(env, brain,training_num):
    reward_sum = 0
    average_reward_line = []
    training_time = []
    average_reward = 0
    batch = 32
    for i in range(training_num):
        total_reward = 0
        observation = env.reset()
        done = False
        sample = Sample(env,brain)
        while True:
            # 采样数据
            sample_states, sample_actions, sample_rs, done,observation,rr = sample.sample_steps(observation,batch, done)
            total_reward+=rr
            # env.render()
            # 训练AC网络
            brain.train_step(sample_states, sample_actions, sample_rs)
            # print(done)
            if done:
                break
        if i == 0:
            average_reward = total_reward
        else:
            average_reward = 0.95*average_reward + 0.05*total_reward
        # print(loss.shape)
        print("current experiments%d, average_reward is %f"%(i, average_reward))
        average_reward_line.append(average_reward)
        training_time.append(i)
        if average_reward > -300:
            break
    brain.save_model('./current_bset_ppo_pendulum')
    plt.plot(training_time, average_reward_line)
    plt.xlabel("training number")
    plt.ylabel("score")
    plt.show()
def policy_test(env, policy,test_num):
    for i in range(test_num):
        reward_sum = 0
        observation = env.reset()
        print("第%d次测试，初始状态:%f,%f,%f" % (i, observation[0], observation[1], observation[2]))
        # 将一个episode的回报存储起来
        while True:
            env.render()
            # 根据策略网络产生一个动作
            state = np.reshape(observation, [1, 3])
            action = policy.choose_action(state)
            observation_, reward, done, info = env.step(action)
            reward_sum += reward
            if done:
                print("第%d次测试总回报%f" % (i,reward_sum))
                break
            time.sleep(0.01)
            observation = observation_
if __name__=='__main__':
    #创建仿真环境
    env_name = 'Pendulum-v0'
    env = gym.make(env_name)
    env.unwrapped
    env.seed(1)
    #力矩界限
    action_bound = [-env.action_space.high, env.action_space.high]
    #实例化策略网络
    brain = Policy_Net(env,action_bound)
    #最大训练次数
    training_num = 5000
    #利用ppo算法训练神经网络
    policy_train(env, brain, training_num)
    #对训练好的神经网络进行测试
    reward_sum = policy_test(env, brain,100)
